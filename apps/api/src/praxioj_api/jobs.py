"""PostgreSQL-backed job repository. All mutations lock session, run, then job.

An expired lease is failed, never automatically replayed. The remote request may
already have had side effects even if its response was not durably received.
"""
from dataclasses import dataclass
from datetime import timedelta, timezone
from secrets import token_urlsafe

from sqlalchemy import func, or_, select

from praxioj.tracing import EventType
from .job_models import Job
from .models import ProviderCall, SolveSession, User, WorkspaceRun, utcnow
from .services import append_trace


class LeaseLost(Exception):
    """The executor no longer has authority to change this job or its session."""


@dataclass(frozen=True)
class Lease:
    run_id: str
    worker_id: str
    claim_token: str
    fence: int


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def database_now(db):
    # PostgreSQL time is the common lease clock for independent worker machines.
    return db.scalar(select(func.clock_timestamp())) if db.bind.dialect.name == "postgresql" else utcnow()


def locked_rows(db, run_id):
    sid = db.scalar(select(WorkspaceRun.session_id).where(WorkspaceRun.id == run_id))
    if sid is None:
        return None, None, None
    session = db.scalar(select(SolveSession).where(SolveSession.id == sid).with_for_update())
    run = db.scalar(select(WorkspaceRun).where(WorkspaceRun.id == run_id).with_for_update().execution_options(populate_existing=True))
    job = db.scalar(select(Job).where(Job.run_id == run_id).with_for_update().execution_options(populate_existing=True))
    return session, run, job


def owns(job, lease, now):
    return (job is not None and job.state == "RUNNING" and job.worker_id == lease.worker_id
            and job.claim_token == lease.claim_token and job.fence == lease.fence
            and job.lease_expires_at is not None and aware(job.lease_expires_at) > now
            and job.deadline_at is not None and aware(job.deadline_at) > now)


def require_lease(db, lease):
    session, run, job = locked_rows(db, lease.run_id)
    if not owns(job, lease, database_now(db)) or run.status != "running" or session.active_run_id != run.id:
        raise LeaseLost()
    return session, run, job


def enqueue(db, session, run, max_seconds):
    job = Job(run_id=run.id, session_id=session.id, max_seconds=max_seconds, available_at=database_now(db))
    db.add(job)
    db.flush()
    return job


def terminalize(db, session, run, job, status, code=None, provider_details=None):
    """Caller holds all three locks and has either a live lease or control authority."""
    from .runs import finish_locked
    uncertain = db.scalar(select(ProviderCall.id).where(ProviderCall.run_id == run.id,
                                                       ProviderCall.status == "started").limit(1)) is not None
    job.external_effect_uncertain = job.external_effect_uncertain or uncertain
    if code in {"lease_expired", "worker_stopped", "job_timeout", "legacy_run_quarantined"}:
        job.recovery_reason = code
    job.state = {"completed": "COMPLETED", "failed": "FAILED", "cancelled": "CANCELLED"}[status]
    job.finished_at = database_now(db)
    job.claim_token = None
    job.lease_expires_at = None
    job.fence += 1
    finish_locked(db, session, run, status, code, provider_details)


def cancel_locked(db, session, run):
    """Owner-authorized cancellation is persisted before the API responds."""
    job = db.scalar(select(Job).where(Job.run_id == run.id).with_for_update())
    if run.status in {"completed", "failed", "cancelled"}:
        return
    run.cancel_requested = True
    if job is not None:
        terminalize(db, session, run, job, "cancelled", "cancelled")
    else:
        from .runs import finish_locked
        finish_locked(db, session, run, "cancelled", "cancelled")


class JobRepository:
    def __init__(self, session_factory, *, lease_seconds=15):
        self.session_factory = session_factory
        self.lease_seconds = lease_seconds

    def claim(self, worker_id):
        with self.session_factory.begin() as db:
            now = database_now(db)
            # Lock the session first, including for competing claims. The second
            # fresh query below rechecks state after waiting on any existing lock.
            selected = db.execute(select(SolveSession, Job.run_id).join(Job, Job.session_id == SolveSession.id)
                .where(Job.state == "PENDING", Job.available_at <= now)
                .order_by(Job.available_at, Job.run_id).limit(1)
                .with_for_update(of=SolveSession, skip_locked=True)).first()
            if selected is None:
                return None
            session, run_id = selected
            run = db.scalar(select(WorkspaceRun).where(WorkspaceRun.id == run_id).with_for_update())
            if run is None:
                # The foreign key prevents this in a migrated database.
                return None
            job = db.scalar(select(Job).where(Job.run_id == run.id).with_for_update().execution_options(populate_existing=True))
            if job is None or job.state != "PENDING" or aware(job.available_at) > now:
                return None
            if session.active_run_id != run.id or run.status != "queued":
                terminalize(db, session, run, job, "failed", "job_state_conflict")
                return None
            if session.trace_purged_at is not None or session.trace_expires_at is None or aware(session.trace_expires_at) <= now:
                terminalize(db, session, run, job, "failed", "session_expired")
                return None
            user = db.get(User, session.user_id)
            if not user or not user.is_active or not user.username:
                terminalize(db, session, run, job, "failed", "account_unavailable")
                return None
            if run.cancel_requested or session.status != "active":
                terminalize(db, session, run, job, "cancelled", "cancelled")
                return None
            job.state = "RUNNING"
            job.worker_id = worker_id
            job.claim_token = token_urlsafe(32)
            job.fence += 1
            job.attempt += 1
            job.started_at = job.heartbeat_at = now
            job.deadline_at = now + timedelta(seconds=job.max_seconds)
            job.lease_expires_at = min(now + timedelta(seconds=self.lease_seconds), job.deadline_at)
            run.status = "running"
            append_trace(db, session, EventType.SESSION_STATE_CHANGED,
                {"run_status": "running", "job_state": "RUNNING", "attempt": job.attempt, "fence": job.fence},
                resource_ids={"run_id": run.id, "job_id": run.id}, correlation_id=run.id)
            return Lease(run.id, worker_id, job.claim_token, job.fence)

    def heartbeat(self, lease):
        with self.session_factory.begin() as db:
            try:
                session, run, job = require_lease(db, lease)
            except LeaseLost:
                return False
            now = database_now(db)
            job.heartbeat_at = now
            job.lease_expires_at = min(now + timedelta(seconds=self.lease_seconds), aware(job.deadline_at))
            return True

    def recover(self, limit=100):
        """Reconcile only expired leases; an API restart never cancels healthy work."""
        recovered = 0
        for _ in range(limit):
            with self.session_factory.begin() as db:
                now = database_now(db)
                session = db.scalar(select(SolveSession).join(Job, Job.session_id == SolveSession.id)
                    .where(Job.state == "RUNNING", or_(Job.lease_expires_at <= now, Job.deadline_at <= now))
                    .order_by(Job.lease_expires_at, Job.run_id).limit(1)
                    .with_for_update(of=SolveSession, skip_locked=True))
                if session is None:
                    break
                run = db.scalar(select(WorkspaceRun).join(Job, Job.run_id == WorkspaceRun.id)
                    .where(Job.session_id == session.id, Job.state == "RUNNING")
                    .with_for_update(of=WorkspaceRun))
                if run is None:
                    continue
                job = db.scalar(select(Job).where(Job.run_id == run.id).with_for_update().execution_options(populate_existing=True))
                now = database_now(db)
                if job.state != "RUNNING" or (aware(job.lease_expires_at) > now and aware(job.deadline_at) > now):
                    continue
                code = "job_timeout" if aware(job.deadline_at) <= now else "lease_expired"
                terminalize(db, session, run, job, "failed", code)
                recovered += 1
        return recovered
