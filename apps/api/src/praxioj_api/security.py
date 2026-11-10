"""Account authentication, CSRF authorization, and localhost request boundaries."""
from secrets import compare_digest
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from .auth import aware, token_digest
from .models import AuthSession, User, utcnow
from .settings import Settings


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
                message["headers"] = list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)
        await self.app(scope, receive, private_send)
