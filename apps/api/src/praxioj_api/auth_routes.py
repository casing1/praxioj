"""Explicit account and role APIs; private credentials never enter a Trace."""
from secrets import compare_digest, token_urlsafe
import re

from fastapi import HTTPException, Request, Response
from pydantic import Field, SecretStr, field_validator
from sqlalchemy import select, update

from praxioj.problems import ProblemManifest, public_problem
from .auth import PASSWORD_HASHER, aware, consume_auth_attempt, hash_password, issue_session, token_digest, user_public, verify_password
from .models import AuthSession, Problem, ProblemVersion, User, utcnow
from .registry import VersionConflict, register_manifest
from .schemas import RequestModel
from .security import can_manage_problem, reauthenticated_until, require_role, require_user
from .retention import audit


class Credentials(RequestModel):
    username: str = Field(min_length=3, max_length=64)
    password: SecretStr

    @field_validator("username")
    @classmethod
    def normalized_username(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,63}", value):
            raise ValueError("Username must use 3–64 ASCII letters, digits, dots, hyphens or underscores")
        return value

    @field_validator("password")
    @classmethod
    def bounded_password(cls, value):
        password = value.get_secret_value()
        if not 12 <= len(password) <= 1024 or len(password.encode("utf-8")) > 4096:
            raise ValueError("Password must contain 12–1024 characters and at most 4096 UTF-8 bytes")
        return value


class PublishProblem(RequestModel):
    manifest: ProblemManifest


class PasswordConfirmation(RequestModel):
    password: SecretStr

    @field_validator("password")
    @classmethod
    def bounded_password(cls, value):
        return Credentials.bounded_password(value)


class PasswordChange(RequestModel):
    current_password: SecretStr
    new_password: SecretStr

    @field_validator("current_password", "new_password")
    @classmethod
    def bounded_password(cls, value):
        return Credentials.bounded_password(value)


def clear_auth_cookies(response, settings):
    for name in (settings.cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(name, path="/", httponly=True, secure=settings.cookie_secure, samesite="strict")


def install_auth_routes(app):
    def authenticate(body, request, response, registering):
        # JSON + an explicit allowed Origin also prevents login/session-swap CSRF.
        if request.headers.get("origin") not in app.state.settings.allowed_origins:
            raise HTTPException(403, "An allowed Origin is required for authentication")
        error = None
        result = None
        with app.state.session_factory.begin() as db:
            decision = consume_auth_attempt(db, request, body.username)
            response.headers.update(decision.headers)
            if not decision.allowed:
                if decision.first_denial:
                    audit(db, "auth_throttled", purpose="register" if registering else "login")
                error = HTTPException(429, "Too many authentication attempts", headers=decision.headers)
            else:
                user = db.scalar(select(User).where(User.username == body.username).with_for_update())
                password = body.password.get_secret_value()
                if registering:
                    # The same status/body and one Argon2 hash for available and
                    # existing usernames. Never disclose or replace an account.
                    encoded = hash_password(password)
                    if user is None:
                        user = User(username=body.username, password_hash=encoded,
                                    identity_token_hash=token_digest(token_urlsafe(32)), is_active=True, role="participant")
                        db.add(user)
                        db.flush()
                        audit(db, "account_registered", actor_id=user.id, resource_id=user.id)
                    result = {"message": "If registration is available, you can now sign in with these credentials."}
                elif not verify_password(user.password_hash if user and user.is_active else None, password):
                    audit(db, "auth_failed", purpose="login", reason="invalid_credentials")
                    error = HTTPException(401, "Invalid username or password", headers=decision.headers)
                else:
                    if PASSWORD_HASHER.check_needs_rehash(user.password_hash):
                        user.password_hash = hash_password(password)
                    result = issue_session(db, user, request, response)
                    audit(db, "auth_login", actor_id=user.id, resource_id=request.state.auth_session.id)
        # Failure attempts must commit their rate limits instead of rolling back.
        if error:
            raise error
        return result

    @app.post("/api/auth/register", status_code=202)
    def register(body: Credentials, request: Request, response: Response):
        return authenticate(body, request, response, True)

    @app.post("/api/auth/login")
    def login(body: Credentials, request: Request, response: Response):
        return authenticate(body, request, response, False)

    @app.get("/api/auth/me")
    def me(request: Request):
        with app.state.session_factory() as db:
            user = require_user(db, request)
            csrf = request.cookies.get(app.state.settings.csrf_cookie_name, "")
            if not csrf or len(csrf) > 128 or not compare_digest(token_digest(csrf), request.state.auth_session.csrf_hash):
                raise HTTPException(401, "Authentication session is incomplete; sign in again")
            return {"user": user_public(user), "csrf_token": csrf, "expires_at": aware(request.state.auth_session.expires_at),
                    "reauthenticated_until": reauthenticated_until(request)}

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response):
        with app.state.session_factory.begin() as db:
            user = require_user(db, request)
            request.state.auth_session.revoked_at = utcnow()
            audit(db, "auth_logout", actor_id=user.id, resource_id=request.state.auth_session.id)
        clear_auth_cookies(response, app.state.settings)

    @app.get("/api/auth/sessions")
    def sessions(request: Request):
        with app.state.session_factory() as db:
            user = require_user(db, request)
            return [{"id": item.id, "created_at": aware(item.created_at), "expires_at": aware(item.expires_at),
                     "current": item.id == request.state.auth_session.id} for item in db.scalars(
                select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > utcnow()).order_by(AuthSession.created_at.desc(), AuthSession.id.desc()).limit(10))]

    @app.post("/api/auth/sessions/{session_id}/revoke", status_code=204)
    def revoke(session_id: str, request: Request, response: Response):
        with app.state.session_factory.begin() as db:
            user = require_user(db, request)
            target = db.scalar(select(AuthSession).where(AuthSession.id == session_id, AuthSession.user_id == user.id))
            if target is None:
                raise HTTPException(404, "Authentication session not found")
            if target.revoked_at is None:
                target.revoked_at = utcnow()
                audit(db, "auth_session_revoked", actor_id=user.id, resource_id=target.id)
            if target.id == request.state.auth_session.id:
                clear_auth_cookies(response, app.state.settings)

    def confirm(db, request, password, response):
        user = require_user(db, request)
        # Confirmation has a separate bounded purpose. Authenticated mutation
        # paths lock the user before these rows, avoiding login lock inversion.
        decision = consume_auth_attempt(db, request, user.id, purpose="confirmation")
        response.headers.update(decision.headers)
        if not decision.allowed:
            if decision.first_denial:
                audit(db, "auth_throttled", actor_id=user.id, purpose="confirmation")
            return user, HTTPException(429, "Too many authentication attempts", headers=decision.headers)
        if not verify_password(user.password_hash, password.get_secret_value()):
            audit(db, "auth_failed", actor_id=user.id, purpose="confirmation", reason="invalid_credentials")
            return user, HTTPException(403, "Invalid credentials", headers=decision.headers)
        return user, None

    @app.post("/api/auth/reauthenticate")
    def reauthenticate(body: PasswordConfirmation, request: Request, response: Response):
        with app.state.session_factory.begin() as db:
            user, error = confirm(db, request, body.password, response)
            if error is None:
                request.state.auth_session.reauthenticated_at = utcnow()
                audit(db, "auth_confirmed", actor_id=user.id, resource_id=request.state.auth_session.id)
                result = {"expires_at": reauthenticated_until(request)}
        if error:
            raise error
        return result

    @app.post("/api/auth/password", status_code=204)
    def change_password(body: PasswordChange, request: Request, response: Response):
        with app.state.session_factory.begin() as db:
            user, error = confirm(db, request, body.current_password, response)
            if error is None:
                user.password_hash = hash_password(body.new_password.get_secret_value())
                db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
                    .values(revoked_at=utcnow(), reauthenticated_at=None))
                audit(db, "auth_password_changed", actor_id=user.id, resource_id=user.id, sessions_revoked=True)
        if error:
            raise error
        clear_auth_cookies(response, app.state.settings)

    @app.get("/api/admin/users")
    def users(request: Request):
        with app.state.session_factory() as db:
            require_role(db, request, "administrator")
            return [user_public(user) for user in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.username).limit(100))]

    @app.get("/api/author/problems")
    def author_problems(request: Request):
        with app.state.session_factory() as db:
            user = require_role(db, request, "author", "administrator")
            query = select(ProblemVersion).join(Problem, Problem.id == ProblemVersion.problem_id)
            if user.role != "administrator":
                query = query.where(Problem.author_id == user.id)
            return [public_problem(ProblemManifest.model_validate(version.manifest)) for version in
                    db.scalars(query.order_by(ProblemVersion.created_at.desc()).limit(100))]

    @app.post("/api/author/problems", status_code=201)
    def publish(body: PublishProblem, request: Request):
        with app.state.session_factory.begin() as db:
            user = require_role(db, request, "author", "administrator")
            problem = db.scalar(select(Problem).where(Problem.id == body.manifest.id).with_for_update())
            if problem and not can_manage_problem(user, problem):
                raise HTTPException(404, "Problem not found")
            try:
                version = register_manifest(db, body.manifest, author_id=user.id)
            except VersionConflict:
                raise HTTPException(409, "Version already exists with different content") from None
            return {"problem_id": version.problem_id, "version": version.version, "manifest_sha256": version.manifest_sha256}
