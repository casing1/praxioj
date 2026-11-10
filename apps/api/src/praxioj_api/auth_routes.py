"""Explicit account and role APIs; private credentials never enter a Trace."""
from secrets import compare_digest, token_urlsafe
import re

from fastapi import HTTPException, Request, Response
from pydantic import Field, SecretStr, field_validator
from sqlalchemy import select

from praxioj.problems import ProblemManifest, public_problem
from .auth import PASSWORD_HASHER, aware, consume_auth_attempt, hash_password, issue_session, token_digest, user_public, verify_password
from .models import AuthSession, Problem, ProblemVersion, User, utcnow
from .registry import VersionConflict, register_manifest
from .schemas import RequestModel
from .security import can_manage_problem, require_role, require_user


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


def install_auth_routes(app):
    def authenticate(body, request, response, registering):
        # JSON + an explicit allowed Origin also prevents login/session-swap CSRF.
        if request.headers.get("origin") not in app.state.settings.allowed_origins:
            raise HTTPException(403, "An allowed Origin is required for authentication")
        error = None
        result = None
        with app.state.session_factory.begin() as db:
            if not consume_auth_attempt(db, request, body.username):
                error = HTTPException(429, "Too many authentication attempts", headers={"Retry-After": str(app.state.settings.auth_rate_window_seconds)})
            else:
                user = db.scalar(select(User).where(User.username == body.username).with_for_update())
                password = body.password.get_secret_value()
                if registering:
                    if user is not None:
                        # Keep work comparable and return no account metadata.
                        verify_password(None, password)
                        error = HTTPException(409, "Unable to register this username")
                    else:
                        user = User(username=body.username, password_hash=hash_password(password),
                                    identity_token_hash=token_digest(token_urlsafe(32)), is_active=True, role="participant")
                        db.add(user)
                        db.flush()
                elif not verify_password(user.password_hash if user and user.is_active else None, password):
                    error = HTTPException(401, "Invalid username or password")
                if error is None:
                    if PASSWORD_HASHER.check_needs_rehash(user.password_hash):
                        user.password_hash = hash_password(password)
                    result = issue_session(db, user, request, response)
        # Failure attempts must commit their rate limits instead of rolling back.
        if error:
            raise error
        return result

    @app.post("/api/auth/register", status_code=201)
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
            return {"user": user_public(user), "csrf_token": csrf, "expires_at": aware(request.state.auth_session.expires_at)}

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response):
        with app.state.session_factory.begin() as db:
            require_user(db, request)
            request.state.auth_session.revoked_at = utcnow()
        settings = app.state.settings
        for name in (settings.cookie_name, settings.csrf_cookie_name):
            response.delete_cookie(name, path="/", httponly=True, secure=settings.cookie_secure, samesite="strict")

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
