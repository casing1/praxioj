"""Password verification, session issuance, and persistent authentication throttles."""
from datetime import timedelta, timezone
from secrets import token_urlsafe
from hashlib import sha256
from dataclasses import dataclass
from math import ceil

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import case, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .models import AuthRateLimit, AuthSession, User, utcnow

# Explicit RFC 9106 low-memory Argon2id profile, independent of library defaults.
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4,
                                 hash_len=32, salt_len=16, type=Type.ID)
# A dummy verification prevents the ordinary missing-user branch skipping Argon2.
_DUMMY_HASH = PASSWORD_HASHER.hash(token_urlsafe(32))


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(encoded: str | None, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(encoded or _DUMMY_HASH, password) and encoded is not None
    except (VerificationError, InvalidHashError):
        return False


def user_public(user: User):
    return {"id": user.id, "username": user.username, "role": user.role}


def issue_session(db, user, request, response):
    settings = request.app.state.settings
    now = utcnow()
    # Rotate a presented session for this account; never adopt a caller token.
    # Other accounts' rows are not locked while this account lock is held.
    # A client switching accounts should log out first to revoke the old login.
    old_token = request.cookies.get(settings.cookie_name)
    if old_token and len(old_token) <= 128:
        db.execute(update(AuthSession).where(AuthSession.user_id == user.id,
                   AuthSession.token_hash == token_digest(old_token),
                   AuthSession.revoked_at.is_(None)).values(revoked_at=now))
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.expires_at < now))
    # Bound concurrent active sessions per account. New authentication revokes
    # oldest sessions once the fixed cap is reached.
    active = list(db.scalars(select(AuthSession).where(AuthSession.user_id == user.id,
                 AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
                 .order_by(AuthSession.created_at.desc(), AuthSession.id.desc())))
    for old in active[settings.auth_max_sessions - 1:]:
        old.revoked_at = now
    token, csrf = token_urlsafe(32), token_urlsafe(32)
    auth_session = AuthSession(user_id=user.id, token_hash=token_digest(token), csrf_hash=token_digest(csrf),
                               created_at=now, expires_at=now + timedelta(seconds=settings.auth_session_seconds))
    db.add(auth_session)
    db.flush()
    request.state.auth_session = auth_session
    for name, value in ((settings.cookie_name, token), (settings.csrf_cookie_name, csrf)):
        response.set_cookie(name, value, max_age=settings.auth_session_seconds,
            expires=auth_session.expires_at, httponly=True, samesite="strict", secure=settings.cookie_secure, path="/")
    return {"user": user_public(user), "csrf_token": csrf, "expires_at": auth_session.expires_at,
            "reauthenticated_until": None}


@dataclass(frozen=True)
class AuthThrottle:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int
    first_denial: bool = False

    @property
    def headers(self):
        headers = {"RateLimit-Limit": str(self.limit), "RateLimit-Remaining": str(self.remaining),
                   "RateLimit-Reset": str(self.reset_seconds)}
        if not self.allowed:
            headers["Retry-After"] = str(self.reset_seconds)
        return headers


def consume_rate_bucket(db, key, limit, window_seconds, now):
    """Caller commits the short reservation even when the request is rejected."""
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    expired = AuthRateLimit.window_start <= now - timedelta(seconds=window_seconds)
    # One atomic statement both claims capacity and returns its decision. Retain
    # two sentinel values above the cap so only the first denial is audited;
    # repeat denials saturate without counter overflow or extra SELECT/UPDATE.
    statement = insert(AuthRateLimit).values(key_hash=key, window_start=now, count=1)
    statement = statement.on_conflict_do_update(index_elements=["key_hash"], set_={
        "window_start": case((expired, now), else_=AuthRateLimit.window_start),
        "count": case((expired, 1), (AuthRateLimit.count < limit + 2, AuthRateLimit.count + 1), else_=limit + 2),
    }).returning(AuthRateLimit.window_start, AuthRateLimit.count)
    window_start, count = db.execute(statement).one()
    reset = max(1, ceil((aware(window_start) + timedelta(seconds=window_seconds) - now).total_seconds()))
    return AuthThrottle(count <= limit, limit, max(0, limit - count), reset, first_denial=count == limit + 1)


def consume_auth_attempt(db, request, username, *, purpose="auth"):
    """Return a throttle decision; caller commits it even when authentication fails.

    Keys contain purpose-specific hashes, never raw credentials or IP addresses.
    Socket peer address is used; forwarded headers are intentionally ignored.
    """
    settings = request.app.state.settings
    now = utcnow()
    peer = request.client.host if request.client else "unknown"
    keys = [(token_digest(purpose + "-ip:" + peer), settings.auth_ip_limit),
            (token_digest(purpose + "-account:" + username), settings.auth_account_limit)]
    decisions = []
    # Every request locks its IP row before its account row. Stop before creating
    # account keys once the IP budget is exhausted.
    for key, limit in keys:
        decision = consume_rate_bucket(db, key, limit, settings.auth_rate_window_seconds, now)
        if not decision.allowed:
            return decision
        decisions.append(decision)
    # Report the most constrained of the IP/account budgets. Expired bucket
    # cleanup belongs to bounded maintenance, not every authentication request.
    return min(decisions, key=lambda decision: decision.remaining)
