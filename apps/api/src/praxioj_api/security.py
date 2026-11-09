"""Local demo guardrails, not an authentication or isolation solution."""
from hashlib import sha256
from secrets import token_urlsafe
from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from .models import User
from .settings import Settings


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def current_user(db: Session, request: Request) -> User | None:
    token = request.cookies.get(request.app.state.settings.cookie_name)
    if not token or len(token) > 128:
        return None
    return db.scalar(select(User).where(User.identity_token_hash == token_digest(token)))


def require_user(db: Session, request: Request) -> User:
    user = current_user(db, request)
    if user is None:
        raise HTTPException(404, "Resource not found")
    return user


def ensure_user(db: Session, request: Request, response: Response) -> User:
    user = current_user(db, request)
    if user is not None:
        return user
    token = token_urlsafe(32)
    user = User(identity_token_hash=token_digest(token), role="participant")
    db.add(user)
    db.flush()
    response.set_cookie(
        request.app.state.settings.cookie_name, token,
        httponly=True, samesite="strict", secure=False, path="/", max_age=86400 * 7,
    )
    return user


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
