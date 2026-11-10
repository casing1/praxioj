"""Atomic admission and daily policy budgets; never manufacture provider usage.

Account mutation locks precede session/job locks. Admission/bucket locks are last;
no quota function locks User or SolveSession. Callers commit before provider I/O.
"""
from datetime import timedelta
from hashlib import sha256
import json

from fastapi import HTTPException
from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .models import ProblemVersion, ProviderCall, SolveSession, TraceEvent, WorkspaceRun
from .quota_models import AdmissionGate, ProviderReservation, QuotaBucket, TraceUsage
from .jobs import database_now

TERMINAL_EVENT_RESERVE = 128
TERMINAL_BYTE_RESERVE = 4 * 1024 * 1024


class QuotaExceeded(HTTPException):
    def __init__(self, code, retry_after=60):
        self.code = code
        super().__init__(429, code, headers={"Retry-After": str(max(1, int(retry_after))),
            "X-RateLimit-Policy": code})


def day_start(now):
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _key(scope, subject, day):
    return sha256(f"{scope}:{subject}:{day.date().isoformat()}".encode()).hexdigest()


def admission_lock(db):
    # Seeded by migration; fail closed if the coordination row is missing.
    row = db.scalar(select(AdmissionGate).where(AdmissionGate.id == "global").with_for_update())
    if row is None:
        raise HTTPException(503, "Resource admission is unavailable")


def new_session_policy(settings, manifest):
    return {"artifact_max_bytes": min(settings.session_artifact_max_bytes, manifest.resource_limits.max_workspace_bytes),
        "trace_max_events": settings.session_trace_max_events, "trace_max_bytes": settings.session_trace_max_bytes}


def resource_policy(session):
    return session.profile_snapshot.get("resource_policy", {})


def _storage_query(user_id=None):
    policy = SolveSession.profile_snapshot["resource_policy"]
    # Legacy sessions reserve the framework's maximum artifact capacity and the
    # default trace capacity. No existing data is retroactively removed.
    artifact = func.coalesce(policy["artifact_max_bytes"].as_integer(), 1_048_576)
    configured_trace = func.coalesce(policy["trace_max_bytes"].as_integer(), 8 * 1024 * 1024)
    historical_trace = func.coalesce(TraceUsage.terminal_base_bytes, 0)
    trace = case((historical_trace > configured_trace, historical_trace), else_=configured_trace) + TERMINAL_BYTE_RESERVE
    query = select(func.count(SolveSession.id), func.coalesce(func.sum(artifact), 0),
        func.coalesce(func.sum(case((SolveSession.trace_purged_at.is_(None), trace), else_=0)), 0)).outerjoin(
            TraceUsage, TraceUsage.session_id == SolveSession.id)
    return query.where(SolveSession.user_id == user_id) if user_id else query


def admit_session(db, user, manifest, settings):
    """Caller holds User; global lock serializes storage-capacity reservation."""
    admission_lock(db)
    now = database_now(db)
    active = db.scalar(select(func.count()).select_from(SolveSession).where(
        SolveSession.user_id == user.id, SolveSession.status == "active",
        SolveSession.trace_purged_at.is_(None), SolveSession.trace_expires_at > now))
    own_count, own_artifact, own_trace = db.execute(_storage_query(user.id)).one()
    total, all_artifact, all_trace = db.execute(_storage_query()).one()
    policy = new_session_policy(settings, manifest)
    if active >= settings.account_active_sessions or own_count >= settings.account_retained_sessions:
        raise QuotaExceeded("account_session_limit")
    if total >= settings.system_retained_sessions:
        raise QuotaExceeded("system_session_limit")
    if own_artifact + policy["artifact_max_bytes"] > settings.account_artifact_capacity_bytes:
        raise QuotaExceeded("account_artifact_capacity")
    if all_artifact + policy["artifact_max_bytes"] > settings.system_artifact_capacity_bytes:
        raise QuotaExceeded("system_artifact_capacity")
    trace_reservation = policy["trace_max_bytes"] + TERMINAL_BYTE_RESERVE
    if own_trace + trace_reservation > settings.account_trace_capacity_bytes:
        raise QuotaExceeded("account_trace_capacity")
    if all_trace + trace_reservation > settings.system_trace_capacity_bytes:
        raise QuotaExceeded("system_trace_capacity")
    return policy


def admit_run(db, session, settings):
    from .job_models import Job
    admission_lock(db)
    own = db.scalar(select(func.count()).select_from(WorkspaceRun).join(SolveSession,
        WorkspaceRun.session_id == SolveSession.id).where(SolveSession.user_id == session.user_id,
        WorkspaceRun.status.in_(("queued", "running"))))
    if own >= settings.account_active_runs:
        raise QuotaExceeded("account_run_limit")
    pending = db.scalar(select(func.count()).select_from(Job).where(Job.state == "PENDING"))
    if pending >= settings.queue_max_pending:
        raise QuotaExceeded("queue_backpressure")
    check_trace_admission(db, session)


def _scopes(db, session):
    version = db.get(ProblemVersion, session.problem_version_id)
    return [("user", session.user_id), ("problem", version.problem_id), ("system", "global")]


def _buckets(db, scopes, day):
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    result = []
    # Global deterministic order prevents account/problem multi-scope deadlocks.
    for scope, subject in sorted(scopes, key=lambda s: _key(*s, day)):
        key = _key(scope, subject, day)
        db.execute(insert(QuotaBucket).values(key=key, scope=scope, subject=subject, window_start=day,
            model_calls=0, tool_calls=0, input_tokens=0, output_tokens=0, reserved_units=0, uncertain_calls=0)
            .on_conflict_do_nothing(index_elements=["key"]))
        result.append(db.scalar(select(QuotaBucket).where(QuotaBucket.key == key).with_for_update()
            .execution_options(populate_existing=True)))
    return result


def _limits(settings, scope):
    prefix = {"user": "account", "problem": "problem", "system": "system"}[scope]
    return (getattr(settings, prefix + "_daily_model_calls"),
            getattr(settings, prefix + "_daily_tool_calls"),
            getattr(settings, prefix + "_daily_token_allowance"))


def reserve_provider(db, session, call, settings, *, input_bytes, output_limit):
    """Charge a call before dispatch; reserve policy units, not invented tokens.

    The input byte count plus output allowance is a conservative admission policy
    for ordinary compatible tokenizers, not a universal tokenizer or billing bound.
    Unknown/estimated results keep the full reservation until the UTC day expires.
    """
    now = database_now(db)
    day = day_start(now)
    units = max(settings.call_token_reservation, input_bytes + output_limit)
    scopes = _scopes(db, session)
    buckets = _buckets(db, scopes, day)
    retry = (day + timedelta(days=1) - now).total_seconds()
    for row in buckets:
        calls, _, allowance = _limits(settings, row.scope)
        if row.model_calls >= calls:
            raise QuotaExceeded(f"{row.scope}_model_call_limit", retry)
        if row.input_tokens + row.output_tokens + row.reserved_units + units > allowance:
            raise QuotaExceeded(f"{row.scope}_token_allowance", retry)
    for row in buckets:
        row.model_calls += 1
        row.reserved_units += units
        row.uncertain_calls += 1
    problem = next(subject for scope, subject in scopes if scope == "problem")
    db.add(ProviderReservation(call_id=call.id, user_id=session.user_id, problem_id=problem,
        window_start=day, units=units, state="reserved"))


def settle_provider(db, call):
    reservation = db.get(ProviderReservation, call.id)
    if reservation is None or reservation.state != "reserved":
        return
    if call.input_tokens is None or call.output_tokens is None or call.estimated:
        reservation.state = "uncertain"
        return
    rows = _buckets(db, [("user", reservation.user_id), ("problem", reservation.problem_id),
        ("system", "global")], reservation.window_start)
    for row in rows:
        row.reserved_units -= reservation.units
        row.uncertain_calls -= 1
        row.input_tokens += call.input_tokens
        row.output_tokens += call.output_tokens
    reservation.state = "exact"


def reserve_tool(db, session, settings):
    now = database_now(db)
    day = day_start(now)
    rows = _buckets(db, _scopes(db, session), day)
    for row in rows:
        if row.tool_calls >= _limits(settings, row.scope)[1]:
            raise QuotaExceeded(f"{row.scope}_tool_call_limit", (day + timedelta(days=1) - now).total_seconds())
    for row in rows:
        row.tool_calls += 1


def _trace_usage(db, session):
    row = db.get(TraceUsage, session.id)
    if row is None:
        # One-time initialization under the session lock preserves legacy chains.
        total = sum(len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
            for payload in db.scalars(select(TraceEvent.envelope).where(TraceEvent.session_id == session.id)
                .execution_options(stream_results=True, yield_per=32)))
        row = TraceUsage(session_id=session.id, bytes_used=total,
            terminal_base_bytes=total, terminal_base_events=session.next_sequence_number - 1)
        db.add(row)
        db.flush()
    return row


def check_trace_admission(db, session):
    policy = resource_policy(session)
    usage = _trace_usage(db, session)
    if session.next_sequence_number > policy.get("trace_max_events", 2000) or usage.bytes_used >= policy.get("trace_max_bytes", 8 * 1024 * 1024):
        raise QuotaExceeded("trace_storage_limit")


def charge_trace(db, session, envelope, *, terminal=False):
    policy = resource_policy(session)
    row = _trace_usage(db, session)
    size = len(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode())
    count_limit = policy.get("trace_max_events", 2000)
    byte_limit = policy.get("trace_max_bytes", 8 * 1024 * 1024)
    if terminal:
        count_limit = max(count_limit, row.terminal_base_events) + TERMINAL_EVENT_RESERVE
        byte_limit = max(byte_limit, row.terminal_base_bytes) + TERMINAL_BYTE_RESERVE
    if session.next_sequence_number > count_limit or row.bytes_used + size > byte_limit:
        raise QuotaExceeded("trace_storage_limit")
    row.bytes_used += size


def bucket_public(row, settings, scope="user"):
    calls, tools, allowance = _limits(settings, scope)
    return {"model_calls": row.model_calls if row else 0, "tool_calls": row.tool_calls if row else 0,
        "input_tokens": row.input_tokens if row else 0, "output_tokens": row.output_tokens if row else 0,
        "reserved_policy_units": row.reserved_units if row else 0,
        "uncertain_calls": row.uncertain_calls if row else 0,
        "limits": {"model_calls": calls, "tool_calls": tools, "token_allowance": allowance},
        "usage_semantics": "Exact complete provider reports only; unknown or estimated calls retain policy reservations, not billed tokens."}


def account_usage(db, user, settings):
    now = database_now(db)
    day = day_start(now)
    row = db.get(QuotaBucket, _key("user", user.id, day))
    sessions, artifact, trace = db.execute(_storage_query(user.id)).one()
    active_sessions = db.scalar(select(func.count()).select_from(SolveSession).where(SolveSession.user_id == user.id,
        SolveSession.status == "active", SolveSession.trace_purged_at.is_(None), SolveSession.trace_expires_at > now))
    active_runs = db.scalar(select(func.count()).select_from(WorkspaceRun).join(SolveSession,
        WorkspaceRun.session_id == SolveSession.id).where(SolveSession.user_id == user.id,
        WorkspaceRun.status.in_(("queued", "running"))))
    return {"window_start": day, "resets_at": day + timedelta(days=1), "daily": bucket_public(row, settings),
        "active_sessions": active_sessions, "retained_sessions": sessions, "active_runs": active_runs,
        "artifact_capacity_reserved_bytes": artifact, "trace_capacity_reserved_bytes": trace,
        "limits": {"active_sessions": settings.account_active_sessions, "retained_sessions": settings.account_retained_sessions,
            "active_runs": settings.account_active_runs, "artifact_capacity_bytes": settings.account_artifact_capacity_bytes,
            "trace_capacity_bytes": settings.account_trace_capacity_bytes}}


def cleanup_quota_records(db, now, limit=100):
    # Calls are bounded to five minutes, far shorter than the two-day cleanup age.
    # Delete only reservations whose provider call is terminal; stale live attempts
    # remain charged and are reconciled before maintenance attempts cleanup again.
    cutoff = now - timedelta(days=2)
    ids = list(db.scalars(select(ProviderReservation.call_id).join(ProviderCall,
        ProviderCall.id == ProviderReservation.call_id).where(ProviderReservation.window_start < cutoff,
        ProviderCall.status != "started").order_by(ProviderReservation.window_start).limit(limit)))
    if ids:
        db.execute(delete(ProviderReservation).where(ProviderReservation.call_id.in_(ids)))
    live_windows = select(ProviderReservation.window_start).where(ProviderReservation.state == "reserved")
    keys = list(db.scalars(select(QuotaBucket.key).where(QuotaBucket.window_start < cutoff,
        QuotaBucket.window_start.not_in(live_windows))
        .order_by(QuotaBucket.window_start, QuotaBucket.key).limit(limit).with_for_update(skip_locked=True)))
    if keys:
        db.execute(delete(QuotaBucket).where(QuotaBucket.key.in_(keys)))
    return {"reservations": len(ids), "quota_buckets": len(keys)}
