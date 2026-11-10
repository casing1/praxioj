"""Account authentication, CSRF authorization, and localhost request boundaries."""
from secrets import compare_digest
from datetime import timedelta
import asyncio
import logging
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from .auth import aware, consume_rate_bucket, token_digest
from .models import AuthSession, User, utcnow
from .settings import Settings

logger = logging.getLogger("praxioj.internal.security")


def current_user(db: Session, request: Request) -> User | None:
    token = request.cookies.get(request.app.state.settings.cookie_name)
    if not token or len(token) > 128:
        return None
    query = select(User, AuthSession).join(AuthSession, AuthSession.user_id == User.id).where(
        AuthSession.token_hash == token_digest(token), AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > utcnow(), User.is_active.is_(True),
        User.username.is_not(None), User.password_hash.is_not(None),
    )
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        # User first, then solve-session/job locks: account deletion and role
        # changes serialize with every authenticated mutation.
        query = query.with_for_update(of=User)
    row = db.execute(query).first()
    if row is None:
        return None
    auth_session = db.scalar(select(AuthSession).where(AuthSession.id == row[1].id)
                             .execution_options(populate_existing=True))
    if auth_session is None or auth_session.revoked_at is not None or aware(auth_session.expires_at) <= utcnow():
        return None
    request.state.auth_session = auth_session
    return row[0]


def require_user(db: Session, request: Request) -> User:
    user = current_user(db, request)
    if user is None:
        raise HTTPException(401, "Authentication required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or len(csrf) > 128 or not compare_digest(token_digest(csrf), request.state.auth_session.csrf_hash):
            raise HTTPException(403, "CSRF validation failed")
    return user


def require_role(db: Session, request: Request, *roles: str) -> User:
    user = require_user(db, request)
    if user.role not in roles:
        raise HTTPException(403, "Insufficient permissions")
    return user


def reauthenticated_until(request):
    session = request.state.auth_session
    if session.reauthenticated_at is None:
        return None
    return min(aware(session.expires_at), aware(session.reauthenticated_at) + timedelta(
        seconds=request.app.state.settings.auth_reauthentication_seconds))


def require_recent_reauthentication(db: Session, request: Request) -> User:
    """A fresh password confirmation belongs to this server session only.

    Login alone does not confirm a subsequent data export/deletion request.
    require_user refreshes revocation after acquiring the account mutation lock.
    """
    user = require_user(db, request)
    until = reauthenticated_until(request)
    if until is None or until <= utcnow():
        raise HTTPException(403, "Recent password confirmation required")
    return user


def can_manage_problem(user: User, problem) -> bool:
    return user.role == "administrator" or (user.role == "author" and problem.author_id == user.id)


class LocalDevelopmentGuard:
    """Reject remote hostnames, cross-origin writes, and oversized JSON bodies."""
    def __init__(self, app, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        host = headers.get("host", "").lower()
        hostname = host.split(":", 1)[0] if not host.startswith("[") else host.split("]", 1)[0] + "]"
        if hostname not in self.settings.allowed_hosts:
            return await JSONResponse({"detail": "Local development hosts only"}, status_code=400)(scope, receive, send)
        # Health probes remain cheap and do not consume API capacity. All other
        # paths share a persistent socket-peer budget, including rejected routes.
        # No user/solve transaction exists yet, so this cannot invert its locks
        # or require a second pooled connection while holding one.
        rate_headers = {}
        if scope.get("path") not in {"/api/health", "/health"}:
            def reserve_request():
                peer = scope.get("client")
                address = peer[0] if peer else "unknown"
                with scope["app"].state.session_factory.begin() as db:
                    return consume_rate_bucket(db, token_digest("api-ip:" + address), self.settings.api_ip_limit,
                                               self.settings.api_rate_window_seconds, utcnow())
            try:
                decision = await asyncio.to_thread(reserve_request)
            except SQLAlchemyError:
                logger.warning("api_request_rejected code=rate_store_unavailable")
                return await JSONResponse({"detail": "Request admission temporarily unavailable"}, status_code=503,
                    headers={"Cache-Control": "no-store", "Retry-After": "1"})(scope, receive, send)
            rate_headers = decision.headers
            if not decision.allowed:
                logger.info("api_request_rejected code=rate_limited")
                return await JSONResponse({"detail": "Too many API requests"}, status_code=429,
                    headers={**rate_headers, "Cache-Control": "no-store"})(scope, receive, send)
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            origin = headers.get("origin")
            if (origin is not None and origin not in self.settings.allowed_origins) or headers.get("sec-fetch-site") == "cross-site":
                return await JSONResponse({"detail": "Cross-origin writes are not allowed"}, status_code=403)(scope, receive, send)
            if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                return await JSONResponse({"detail": "Expected application/json"}, status_code=415)(scope, receive, send)
            # Consume only a bounded body before FastAPI/Pydantic see it. Content-Length alone
            # is insufficient because an untrusted client may use chunked transfer encoding.
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.settings.max_request_bytes:
                    return await JSONResponse({"detail": "Request body too large"}, status_code=413)(scope, receive, send)
                if not message.get("more_body", False):
                    break
            delivered = False
            original_receive = receive

            async def receive_body():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original_receive()
            receive = receive_body
        async def private_send(message):
            if message["type"] == "http.response.start":
                existing = {name.lower() for name, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
                ] + [(name.lower().encode(), value.encode()) for name, value in rate_headers.items()
                     if name.lower().encode() not in existing]
            await send(message)
        await self.app(scope, receive, private_send)
