"""Bounded trace retention and account erasure; never retain deleted payloads in audit."""
from datetime import timedelta, timezone
from secrets import token_hex

from fastapi import HTTPException
from sqlalchemy import delete, or_, select, update

from praxioj.tracing import verify_trace_chain
from .models import (AuthSession, ConversationMessage, Evaluation, ProviderCall, SolveSession,
                     Submission, TraceEvent, WorkspaceFile, WorkspaceRun, utcnow)
from .retention_models import AuditRecord


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def trace_expired(session, now=None):
    return session.trace_purged_at is not None or session.trace_expires_at is None or aware(session.trace_expires_at) <= (now or utcnow())


def audit(db, action, actor_id=None, resource_id=None, **details):
    # Callers provide only bounded IDs, counts, digest checkpoints and reason codes.
    db.add(AuditRecord(action=action, actor_id=actor_id, resource_id=resource_id, details=details))


def trace_status(db, session):
    from .services import traces_for
    # One session lock protects the checkpoint and event query from concurrent
    # worker appends or retention deletion. Refresh objects loaded before locking.
    db.refresh(session, with_for_update=True)
    expired = trace_expired(session)
    if expired:
        return {"status": "expired", "reason": "retention_expired", "event_count": 0,
                "head_hash": session.trace_head_sha256, "expires_at": session.trace_expires_at}
    integrity = verify_trace_chain(traces_for(db, session.id), session_id=session.id,
        expected_head=session.trace_head_sha256, expected_next_sequence=session.next_sequence_number)
    return {**integrity.model_dump(mode="json"), "expires_at": session.trace_expires_at}


def visible_trace(db, session):
    from .services import traces_for
    if trace_expired(session):
        raise HTTPException(410, "Trace data expired under the session retention policy")
    return traces_for(db, session.id)


def purge_expired(factory, settings, now=None, limit=100):
    """One bounded batch; skips live jobs whose terminalization must precede purge."""
    now = now or utcnow()
    from .quota_models import TraceUsage
    with factory.begin() as db:
        sessions = list(db.scalars(select(SolveSession).where(
            SolveSession.trace_purged_at.is_(None), SolveSession.active_run_id.is_(None),
            or_(SolveSession.trace_expires_at <= now, SolveSession.trace_expires_at.is_(None)),
        ).order_by(SolveSession.created_at, SolveSession.id).limit(min(max(limit, 1), 1000))
            .with_for_update(skip_locked=True)))
        for session in sessions:
            count = db.execute(delete(TraceEvent).where(TraceEvent.session_id == session.id)).rowcount
            session.trace_purged_at = now
            if session.status == "active":
                session.status = "ended"
            audit(db, "trace_expired", resource_id=session.id, deleted_events=count,
                  last_sequence=session.next_sequence_number - 1, head_sha256=session.trace_head_sha256)
        if sessions:
            db.execute(update(TraceUsage).where(TraceUsage.session_id.in_([row.id for row in sessions])).values(bytes_used=0))
        expired_audit = list(db.scalars(select(AuditRecord.id)
            .where(AuditRecord.created_at < now - timedelta(days=settings.audit_retention_days))
            .order_by(AuditRecord.created_at, AuditRecord.id).limit(min(max(limit, 1), 1000))
            .with_for_update(skip_locked=True)))
        if expired_audit:
            db.execute(delete(AuditRecord).where(AuditRecord.id.in_(expired_audit)))
        return len(sessions)


def erase_account(db, user):
    """Erase participant content atomically; retain an inactive pseudonymous FK tombstone."""
    from .job_models import Job
    from .quota_models import QuotaBucket
    sessions = list(db.scalars(select(SolveSession).where(SolveSession.user_id == user.id)
        .order_by(SolveSession.id).with_for_update()))
    if any(session.active_run_id for session in sessions):
        raise HTTPException(409, "Cancel active AI runs before deleting your account")
    if not sessions and not user.is_active:
        return {"deleted_sessions": 0}
    # Fixed table-wise deletes replace one delete sequence per solve session.
    # The owner lock and all session locks remain held until the caller commits.
    session_ids = select(SolveSession.id).where(SolveSession.user_id == user.id)
    submission_ids = select(Submission.id).where(Submission.session_id.in_(session_ids))
    db.execute(delete(Evaluation).where(Evaluation.submission_id.in_(submission_ids)))
    for model in (Submission, ProviderCall, Job, WorkspaceRun, ConversationMessage, WorkspaceFile):
        db.execute(delete(model).where(model.session_id.in_(session_ids)))
    deleted_events = db.execute(delete(TraceEvent).where(TraceEvent.session_id.in_(session_ids))).rowcount
    db.execute(delete(SolveSession).where(SolveSession.user_id == user.id))
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(delete(QuotaBucket).where(QuotaBucket.scope == "user", QuotaBucket.subject == user.id))
    user.username = None
    user.password_hash = None
    user.identity_token_hash = token_hex(32)
    user.is_active = False
    user.role = "participant"
    # Problem ownership is deliberately not transferred to another real account.
    audit(db, "account_erased", actor_id=user.id, resource_id=user.id,
          deleted_sessions=len(sessions), deleted_events=deleted_events)
    return {"deleted_sessions": len(sessions)}


def main():
    from .database import make_engine, session_factory
    from .settings import Settings
    settings = Settings()
    engine = make_engine(settings.database_url)
    try:
        count = purge_expired(session_factory(engine), settings)
        print(f"Expired trace sessions purged: {count}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
