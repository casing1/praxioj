"""Transactional synthetic Judge broker; no host process, network or code execution.

The AI runtime queue remains separate. Mutations lock user, solve session, Judge
job and attempt before the shared admission gate. Backend calls happen only after
the claim transaction commits. A failed/expired attempt is never auto-replayed.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256
from secrets import compare_digest, token_urlsafe
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, or_, select

from praxioj.execution import (FIXTURE_SUBMISSION_CONTENT, MOCK_FIXTURE_ID,
    build_mock_request, canonical_digest, parse_execution_request, request_digest)
from praxioj.evaluation.execution import validate_and_assess_synthetic_execution
from praxioj.problems import manifest_digest

from .auth import token_digest
from .backup import assert_not_restored_database
from .jobs import aware, database_now
from .judge_models import JudgeAttempt, JudgeJob, judge_public
from .models import ProblemVersion, SolveSession, Submission, User
from .quotas import admission_lock
from .retention import audit, trace_expired, trace_status
from .services import manifest_for

ACTIVE_STATES = ("PENDING", "RUNNING")
TERMINAL_STATES = ("COMPLETED", "FAILED", "CANCELLED")
RESULT_RESERVATION_BYTES = 65_536
METADATA_LIMIT_MULTIPLIER = 4
AUDIENCE = "mock-judge"
OPERATION = "submit_result"
TERMINAL_AUTHORITY_ERRORS = {"execution_authority_expired", "request_snapshot_changed",
    "request_snapshot_invalid", "request_digest_mismatch", "trace_expired",
    "submission_snapshot_invalid", "synthetic_fixture_required", "problem_snapshot_changed", "submission_not_final"}


class JudgeError(Exception):
    """Only controlled codes cross the API boundary; no raw validation details."""
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


@dataclass(frozen=True)
class JudgeLease:
    job_id: str
    attempt_id: str
    worker_id: str
    fence: int
    token: str = field(repr=False)
    request: object = field(repr=False)


@dataclass(frozen=True)
class JudgeRenewal:
    """Server-observed lease acknowledgement; contains no reusable authority."""
    attempt_id: str
    fence: int
    heartbeat_at: datetime
    lease_expires_at: datetime
    expires_at: datetime
    deadline_at: datetime


def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise JudgeError("invalid_identifier", 422) from None


def _owner(db, owner_id, *, lock=True):
    query = select(User).where(User.id == owner_id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    owner = db.scalar(query)
    if not owner or not owner.is_active or not owner.username or not owner.password_hash:
        raise JudgeError("account_unavailable", 401)
    if owner.role != "administrator":
        raise JudgeError("insufficient_permissions", 403)
    return owner


def _source(db, owner, submission_id, *, lock=True, skip_locked=False):
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise JudgeError("resource_not_found", 404)
    query = select(SolveSession).where(SolveSession.id == submission.session_id,
        SolveSession.user_id == owner.id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update(skip_locked=skip_locked)
    session = db.scalar(query)
    if session is None:
        raise JudgeError("resource_not_found", 404)
    # Refresh the submission only after its owning session is locked.
    db.refresh(submission)
    return session, submission


def _metadata(submission):
    """Recompute content hashes before copying bounded metadata, never file bytes."""
    if submission.content != FIXTURE_SUBMISSION_CONTENT or sha256(submission.content.encode()).hexdigest() != submission.content_sha256:
        raise JudgeError("synthetic_fixture_required", 422)
    if not isinstance(submission.artifacts, list) or len(submission.artifacts) > 100:
        raise JudgeError("submission_snapshot_invalid", 422)
    result = []
    for artifact in submission.artifacts:
        if not isinstance(artifact, dict) or not isinstance(artifact.get("content"), str):
            raise JudgeError("submission_snapshot_invalid", 422)
        try:
            content = artifact["content"].encode("utf-8")
        except UnicodeError:
            raise JudgeError("submission_snapshot_invalid", 422) from None
        if len(content) > 1_048_576 or sha256(content).hexdigest() != artifact.get("sha256"):
            raise JudgeError("submission_snapshot_invalid", 422)
        result.append({"id": artifact.get("id"), "name": artifact.get("name"),
            "media_type": artifact.get("media_type", "text/plain"),
            "size_bytes": len(content), "sha256": artifact["sha256"]})
    return result


def _request(job, attempt):
    try:
        if canonical_digest(job.spec) != job.spec_digest:
            raise JudgeError("request_snapshot_changed")
        # Retain the original policy/image/schema, not current code defaults.
        # Only server-authoritative per-attempt correlation values change here.
        return parse_execution_request({**job.spec["request_template"],
            "request_id": attempt.request_id, "job_id": job.id, "attempt_id": attempt.id,
            "session_id": job.session_id, "fence": attempt.fence,
            "deadline": aware(attempt.deadline_at).isoformat()})
    except JudgeError:
        raise
    except Exception:
        raise JudgeError("request_snapshot_invalid") from None


class JudgeBroker:
    def __init__(self, factory, settings):
        self.factory, self.settings = factory, settings

    def _enabled(self):
        if self.settings.judge_backend != "mock":
            raise JudgeError("runtime_unavailable", 503)

    def _binding(self, db, owner, session, submission, spec=None, *, now=None):
        now = now or database_now(db)
        if trace_expired(session, now):
            raise JudgeError("trace_expired", 410)
        if session.status != "submitted" or session.active_run_id:
            raise JudgeError("submission_not_final")
        version, manifest = manifest_for(db, session)
        if version.problem_id != "release-plan" or version.version != "1.0.0":
            raise JudgeError("synthetic_fixture_required", 422)
        if manifest_digest(manifest) != version.manifest_sha256:
            raise JudgeError("problem_snapshot_changed")
        metadata = _metadata(submission)
        if spec is not None:
            if (spec["problem_version_id"] != version.id or spec["manifest_sha256"] != version.manifest_sha256
                or spec["submission_sha256"] != submission.content_sha256
                or spec["submitted_artifacts"] != metadata
                or spec["trace_head_sha256"] != session.trace_head_sha256
                or spec["trace_next_sequence_number"] != session.next_sequence_number):
                raise JudgeError("request_snapshot_changed")
        return version, manifest, metadata

    def enqueue(self, db, owner, submission_id, request_id, fixture_id=MOCK_FIXTURE_ID):
        self._enabled()
        assert_not_restored_database(db.connection())
        owner = _owner(db, owner.id)
        submission_id, request_id = _uuid(submission_id), _uuid(request_id)
        session, submission = _source(db, owner, submission_id)
        existing = db.scalar(select(JudgeJob).where(JudgeJob.owner_id == owner.id,
            JudgeJob.request_id == request_id).with_for_update())
        if existing:
            if existing.submission_id != submission_id or existing.fixture_id != fixture_id:
                raise JudgeError("idempotency_conflict")
            return existing
        if fixture_id != MOCK_FIXTURE_ID:
            raise JudgeError("synthetic_fixture_required", 422)
        version, manifest, metadata = self._binding(db, owner, session, submission)
        integrity = trace_status(db, session)
        if integrity["status"] != "verified":
            raise JudgeError("trace_integrity_invalid")
        spec = {"problem_version_id": version.id, "manifest_sha256": version.manifest_sha256,
            "submission_sha256": submission.content_sha256, "submitted_artifacts": metadata,
            "trace_head_sha256": session.trace_head_sha256,
            "trace_next_sequence_number": session.next_sequence_number,
            "criteria": [{"id": item.id, "title": item.title, "max_score": item.max_score}
                for item in manifest.evaluation.criteria]}
        now = database_now(db)
        deadline = min(now + timedelta(seconds=60), aware(session.trace_expires_at))
        job_id = str(uuid4())
        try:
            template = build_mock_request(request_id=str(uuid4()), job_id=job_id,
                attempt_id=str(uuid4()), session_id=session.id, fence=1,
                submission_id=submission.id, trace_head_sha256=session.trace_head_sha256,
                trace_next_sequence_number=session.next_sequence_number, deadline=deadline,
                criteria=spec["criteria"], submitted_artifacts=metadata)
            if template.policy.max_result_bytes > RESULT_RESERVATION_BYTES:
                raise JudgeError("policy_exceeds_reservation")
            spec["request_template"] = template.model_dump(mode="json")
        except JudgeError:
            raise
        except Exception:
            raise JudgeError("submission_snapshot_invalid", 422) from None
        job = JudgeJob(id=job_id, owner_id=owner.id, session_id=session.id,
            submission_id=submission.id, request_id=request_id, fixture_id=fixture_id,
            spec=spec, spec_digest=canonical_digest(spec), reserved_output_bytes=RESULT_RESERVATION_BYTES,
            reservation_active=True, state="PENDING", fence=0, created_at=now, deadline_at=deadline)
        admission_lock(db)
        active = db.scalar(select(func.count()).select_from(JudgeJob).where(
            JudgeJob.owner_id == owner.id, JudgeJob.state.in_(ACTIVE_STATES)))
        pending = db.scalar(select(func.count()).select_from(JudgeJob).where(JudgeJob.state == "PENDING"))
        retained = db.execute(select(func.count(), func.count().filter(JudgeJob.owner_id == owner.id),
            func.count().filter(JudgeJob.evidence_purged_at.is_(None)),
            func.count().filter(JudgeJob.owner_id == owner.id, JudgeJob.evidence_purged_at.is_(None)))
            .select_from(JudgeJob)).one()
        reserved = db.execute(select(func.coalesce(func.sum(JudgeJob.reserved_output_bytes), 0),
            func.coalesce(func.sum(JudgeJob.reserved_output_bytes).filter(JudgeJob.owner_id == owner.id), 0))
            .where(JudgeJob.reservation_active.is_(True))).one()
        if (active >= self.settings.judge_account_active_jobs or pending >= self.settings.judge_max_pending
            or retained[3] >= self.settings.judge_account_retained_jobs
            or retained[2] >= self.settings.judge_system_retained_jobs
            or retained[1] >= self.settings.judge_account_retained_jobs * METADATA_LIMIT_MULTIPLIER
            or retained[0] >= self.settings.judge_system_retained_jobs * METADATA_LIMIT_MULTIPLIER
            or reserved[1] + RESULT_RESERVATION_BYTES > self.settings.judge_account_reserved_output_bytes
            or reserved[0] + RESULT_RESERVATION_BYTES > self.settings.judge_system_reserved_output_bytes):
            raise JudgeError("judge_capacity_exceeded", 429)
        db.add(job)
        db.flush()
        audit(db, "judge_enqueued", actor_id=owner.id, resource_id=job.id,
            session_id=session.id, provenance="synthetic_mock", reserved_output_bytes=RESULT_RESERVATION_BYTES)
        return job

    def get_owned(self, db, owner, job_id, *, lock=False):
        owner = _owner(db, owner.id, lock=lock)
        row = db.scalar(select(JudgeJob).where(JudgeJob.id == _uuid(job_id), JudgeJob.owner_id == owner.id))
        if row is None:
            raise JudgeError("resource_not_found", 404)
        _source(db, owner, row.submission_id, lock=lock)
        if lock:
            row = db.scalar(select(JudgeJob).where(JudgeJob.id == row.id).with_for_update()
                .execution_options(populate_existing=True))
        return row

    def _locked(self, db, job_id, *, skip_locked=False):
        owner_id = db.scalar(select(JudgeJob.owner_id).where(JudgeJob.id == job_id))
        if owner_id is None:
            raise JudgeError("resource_not_found", 404)
        owner = db.scalar(select(User).where(User.id == owner_id).with_for_update(skip_locked=skip_locked)
            .execution_options(populate_existing=True))
        if owner is None:
            raise JudgeError("resource_not_found", 404)
        identity = db.execute(select(JudgeJob.session_id, JudgeJob.submission_id).where(JudgeJob.id == job_id)).first()
        if identity is None:
            raise JudgeError("resource_not_found", 404)
        session, submission = _source(db, owner, identity.submission_id, skip_locked=skip_locked)
        job = db.scalar(select(JudgeJob).where(JudgeJob.id == job_id).with_for_update()
            .execution_options(populate_existing=True))
        attempt = db.scalar(select(JudgeAttempt).where(JudgeAttempt.job_id == job.id)
            .with_for_update().execution_options(populate_existing=True))
        return owner, session, submission, job, attempt

    def _finish(self, db, job, attempt, state, code=None):
        now = database_now(db)
        if job.state in TERMINAL_STATES:
            return
        job.state, job.error_code, job.finished_at = state, code, now
        job.fence += 1
        job.reservation_active = False
        if attempt is not None:
            attempt.revoked_at = now
        audit(db, "judge_terminal", actor_id=job.owner_id, resource_id=job.id,
            state=state, code=code, provenance="synthetic_mock")

    def claim(self, worker_id, job_id=None):
        self._enabled()
        if not isinstance(worker_id, str) or not 1 <= len(worker_id) <= 64 or not worker_id.isascii():
            raise JudgeError("invalid_worker_identity", 422)
        if job_id is not None:
            job_id = _uuid(job_id)
        with self.factory.begin() as db:
            assert_not_restored_database(db.connection())
            query = select(User, JudgeJob.id).join(JudgeJob, JudgeJob.owner_id == User.id).where(JudgeJob.state == "PENDING")
            if job_id is not None:
                query = query.where(JudgeJob.id == job_id)
            selected = db.execute(query.order_by(JudgeJob.created_at, JudgeJob.id).limit(1)
                .with_for_update(of=User, skip_locked=True)).first()
            if selected is None:
                return None
            try:
                owner, session, submission, job, previous = self._locked(db, selected[1])
            except JudgeError:
                # Account erasure deletes these jobs; role changes leave no authority.
                return None
            if job.state != "PENDING" or previous is not None:
                return None
            now = database_now(db)
            try:
                if not owner.is_active or not owner.username or not owner.password_hash or owner.role != "administrator":
                    raise JudgeError("account_unavailable")
                self._binding(db, owner, session, submission, job.spec)
                if aware(job.deadline_at) <= now:
                    raise JudgeError("job_timeout")
            except JudgeError as error:
                self._finish(db, job, previous, "FAILED", error.code)
                return None
            admission_lock(db)
            if db.scalar(select(func.count()).select_from(JudgeJob).where(JudgeJob.state == "RUNNING")) >= self.settings.judge_max_running:
                return None
            token = token_urlsafe(32)
            job.state = "RUNNING"
            job.fence += 1
            attempt = JudgeAttempt(id=str(uuid4()), job_id=job.id, request_id=str(uuid4()), fence=job.fence,
                worker_id=worker_id, capability_hash=token_digest(token), audience=AUDIENCE, operation=OPERATION,
                created_at=now, heartbeat_at=now, deadline_at=job.deadline_at, expires_at=job.deadline_at,
                lease_expires_at=min(now + timedelta(seconds=self.settings.judge_lease_seconds), aware(job.deadline_at)),
                request_digest="0" * 64)
            try:
                request = _request(job, attempt)
            except JudgeError as error:
                self._finish(db, job, None, "FAILED", error.code)
                return None
            attempt.request_digest = request_digest(request)
            db.add(attempt)
            db.flush()
            audit(db, "judge_claimed", actor_id=owner.id, resource_id=job.id, attempt_id=attempt.id, fence=job.fence)
            return JudgeLease(job.id, attempt.id, worker_id, job.fence, token, request)

    def _authorize(self, db, lease, *, audience=AUDIENCE, operation=OPERATION):
        owner, session, submission, job, attempt = self._locked(db, lease.job_id)
        if not owner.is_active or not owner.username or not owner.password_hash or owner.role != "administrator":
            raise JudgeError("account_unavailable", 403)
        if (attempt is None or attempt.id != lease.attempt_id or attempt.worker_id != lease.worker_id
            or attempt.fence != lease.fence or job.fence != lease.fence or job.state != "RUNNING"
            or attempt.consumed_at is not None or attempt.revoked_at is not None):
            raise JudgeError("attempt_not_current")
        if (audience != attempt.audience or operation != attempt.operation
            or not isinstance(lease.token, str) or len(lease.token) > 128
            or not compare_digest(token_digest(lease.token), attempt.capability_hash)):
            raise JudgeError("capability_invalid", 403)
        now = database_now(db)
        if aware(attempt.expires_at) <= now or aware(attempt.lease_expires_at) <= now or aware(job.deadline_at) <= now:
            raise JudgeError("execution_authority_expired")
        request = _request(job, attempt)
        try:
            if request_digest(request) != attempt.request_digest or request_digest(lease.request) != attempt.request_digest:
                raise JudgeError("request_digest_mismatch")
        except JudgeError:
            raise
        except Exception:
            raise JudgeError("request_digest_mismatch") from None
        # Reuse this locked authorization instant; renewal and result consumption
        # still perform a fresh DB-time check after all source/result validation.
        self._binding(db, owner, session, submission, job.spec, now=now)
        return owner, session, submission, job, attempt, request

    def renew(self, lease):
        """Renew current authority using the DB clock; invalid clients never gain time."""
        with self.factory.begin() as db:
            assert_not_restored_database(db.connection())
            try:
                owner, session, submission, job, attempt, request = self._authorize(db, lease)
            except JudgeError as error:
                if error.code in TERMINAL_AUTHORITY_ERRORS:
                    *_, job, attempt = self._locked(db, lease.job_id)
                    self._finish(db, job, attempt, "FAILED", error.code)
                return None
            now = database_now(db)
            # Recheck after full source/digest validation; no client timestamp is used.
            code = ("trace_expired" if trace_expired(session, now) else
                "execution_authority_expired" if now >= min(aware(attempt.expires_at),
                    aware(attempt.lease_expires_at), aware(attempt.deadline_at), aware(job.deadline_at)) else None)
            if code:
                self._finish(db, job, attempt, "FAILED", code)
                return None
            attempt.heartbeat_at = now
            attempt.lease_expires_at = min(now + timedelta(seconds=self.settings.judge_lease_seconds),
                aware(attempt.deadline_at), aware(attempt.expires_at))
            return JudgeRenewal(attempt.id, attempt.fence, now, attempt.lease_expires_at,
                aware(attempt.expires_at), aware(attempt.deadline_at))

    def heartbeat(self, lease):
        """M5-compatible boolean facade over the acknowledged renewal operation."""
        return self.renew(lease) is not None

    def cancelled(self, lease):
        """Confirm persisted owner cancellation to a bound, still-unexpired channel.

        This is a stop notification, never permission to cancel or revive a job.
        A terminal fence, original capability and original request must all match.
        """
        with self.factory.begin() as db:
            assert_not_restored_database(db.connection())
            try:
                owner, _, _, job, attempt = self._locked(db, lease.job_id)
                if (not owner.is_active or owner.role != "administrator" or attempt is None
                    or job.state != "CANCELLED" or job.error_code != "cancelled"
                    or job.fence != lease.fence + 1 or attempt.fence != lease.fence
                    or attempt.id != lease.attempt_id or attempt.worker_id != lease.worker_id
                    or attempt.revoked_at is None or attempt.consumed_at is not None
                    or aware(attempt.expires_at) <= database_now(db)
                    or not isinstance(lease.token, str) or len(lease.token) > 128
                    or not compare_digest(token_digest(lease.token), attempt.capability_hash)):
                    return False
                request = _request(job, attempt)
                return request_digest(request) == attempt.request_digest == request_digest(lease.request)
            except JudgeError:
                return False
            except (TypeError, ValueError, AttributeError):
                return False

    def complete(self, lease, raw_result, *, audience=AUDIENCE, operation=OPERATION):
        self._enabled()
        rejection = None
        with self.factory.begin() as db:
            assert_not_restored_database(db.connection())
            try:
                owner, session, submission, job, attempt, request = self._authorize(db, lease, audience=audience, operation=operation)
            except JudgeError as error:
                # These errors arise only after the current opaque capability
                # matched. Commit revocation/release, then reject outside the
                # transaction. Invalid tokens/audiences never cancel live work.
                if error.code not in TERMINAL_AUTHORITY_ERRORS:
                    raise
                *_, job, attempt = self._locked(db, lease.job_id)
                self._finish(db, job, attempt, "FAILED", error.code)
                rejection = error
            if rejection is None:
                try:
                    result, assessment = validate_and_assess_synthetic_execution(request, raw_result)
                except Exception:
                    self._finish(db, job, attempt, "FAILED", "invalid_result")
                    return judge_public(job)
                # Validation may take time. Recheck the authoritative clock at
                # consumption, so expiry during validation cannot accept a result.
                now = database_now(db)
                code = ("trace_expired" if trace_expired(session, now) else
                    "execution_authority_expired" if now >= min(aware(attempt.expires_at),
                        aware(attempt.lease_expires_at), aware(attempt.deadline_at), aware(job.deadline_at)) else None)
                if code:
                    self._finish(db, job, attempt, "FAILED", code)
                    rejection = JudgeError(code)
                else:
                    # Consume only after every authority and content check succeeds.
                    attempt.consumed_at = now
                    job.result = result.model_dump(mode="json")
                    job.assessment = assessment.model_dump(mode="json")
                    state = "COMPLETED" if result.status == "completed" else "CANCELLED" if result.status == "cancelled" else "FAILED"
                    self._finish(db, job, attempt, state, None if state == "COMPLETED" else "synthetic_" + result.status)
                    return judge_public(job)
        raise rejection

    def fail(self, lease, code="backend_error"):
        if code not in {"backend_error", "backend_timeout", "worker_stopped", "backend_unavailable"}:
            code = "backend_error"
        with self.factory.begin() as db:
            assert_not_restored_database(db.connection())
            try:
                *_, job, attempt, request = self._authorize(db, lease)
            except JudgeError:
                return False
            self._finish(db, job, attempt, "FAILED", code)
            return True

    def cancel(self, db, owner, job_id):
        assert_not_restored_database(db.connection())
        job = self.get_owned(db, owner, job_id, lock=True)
        attempt = db.scalar(select(JudgeAttempt).where(JudgeAttempt.job_id == job.id).with_for_update())
        self._finish(db, job, attempt, "CANCELLED", "cancelled")
        return job

    def purge_history(self, limit=100):
        """Bounded independent maintenance; terminal evidence and metadata have separate TTLs.

        A lightweight assessment tombstone survives payload removal. Its explicit
        evidence status prevents a retained score from implying available output.
        Original submission evaluations and Trace checkpoints are never modified.
        """
        limit = min(max(limit, 1), 1000)
        counts = {"purged_judge_payloads": 0, "deleted_judge_jobs": 0,
            "deleted_judge_attempts": 0, "reconciled_judge_reservations": 0}
        with self.factory() as db:
            assert_not_restored_database(db.connection())
            now = database_now(db)
            payload_cutoff = now - timedelta(days=self.settings.judge_result_retention_days)
            metadata_cutoff = now - timedelta(days=self.settings.judge_metadata_retention_days)
            ids = list(db.scalars(select(JudgeJob.id).where(JudgeJob.state.in_(TERMINAL_STATES),
                JudgeJob.finished_at <= payload_cutoff,
                or_(JudgeJob.evidence_purged_at.is_(None), JudgeJob.finished_at <= metadata_cutoff))
                .order_by(JudgeJob.finished_at, JudgeJob.id).limit(limit)))
        for job_id in ids:
            with self.factory.begin() as db:
                assert_not_restored_database(db.connection())
                identity = db.execute(select(JudgeJob.owner_id, JudgeJob.session_id)
                    .where(JudgeJob.id == job_id)).first()
                if identity is None:
                    continue
                # Match admission, account erasure and result delivery lock order.
                # Do not load the participant Submission merely to erase history.
                owner = db.scalar(select(User).where(User.id == identity.owner_id)
                    .with_for_update(skip_locked=True))
                if owner is None:
                    continue
                session = db.scalar(select(SolveSession).where(SolveSession.id == identity.session_id,
                    SolveSession.user_id == owner.id).with_for_update(skip_locked=True))
                if session is None:
                    continue
                job = db.scalar(select(JudgeJob).where(JudgeJob.id == job_id).with_for_update()
                    .execution_options(populate_existing=True))
                if job is None:
                    continue
                attempts = list(db.scalars(select(JudgeAttempt).where(JudgeAttempt.job_id == job.id)
                    .order_by(JudgeAttempt.id).with_for_update().execution_options(populate_existing=True)))
                now = database_now(db)
                if (job.state not in TERMINAL_STATES or job.finished_at is None
                    or aware(job.finished_at) > now - timedelta(days=self.settings.judge_result_retention_days)):
                    continue
                # Fail closed for anomalous terminal rows with outstanding authority.
                # Expired active jobs are terminalized by recovery, not deleted here.
                if any(item.revoked_at is None and item.consumed_at is None
                    and aware(item.expires_at) > now for item in attempts):
                    continue
                if job.reservation_active:
                    job.reservation_active = False
                    counts["reconciled_judge_reservations"] += 1
                hard_delete = aware(job.finished_at) <= now - timedelta(days=self.settings.judge_metadata_retention_days)
                if not hard_delete and job.evidence_purged_at is not None:
                    continue
                counts["deleted_judge_attempts"] += len(attempts)
                db.execute(delete(JudgeAttempt).where(JudgeAttempt.job_id == job.id))
                if hard_delete:
                    audit(db, "judge_history_deleted", actor_id=owner.id, resource_id=job.id,
                        deleted_attempts=len(attempts), provenance="synthetic_mock")
                    db.delete(job)
                    counts["deleted_judge_jobs"] += 1
                else:
                    job.result = None
                    job.spec = {}
                    job.evidence_purged_at = now
                    audit(db, "judge_evidence_purged", actor_id=owner.id, resource_id=job.id,
                        deleted_attempts=len(attempts), evidence_status="unavailable", provenance="synthetic_mock")
                    counts["purged_judge_payloads"] += 1
        return counts

    def recover(self, limit=100):
        limit = min(max(limit, 1), 1000)
        recovered = 0
        with self.factory() as db:
            assert_not_restored_database(db.connection())
            ids = list(db.scalars(select(JudgeJob.id).outerjoin(JudgeAttempt, JudgeAttempt.job_id == JudgeJob.id)
                .join(SolveSession, SolveSession.id == JudgeJob.session_id)
                .join(User, User.id == JudgeJob.owner_id)
                .where(JudgeJob.state.in_(ACTIVE_STATES), or_(JudgeJob.deadline_at <= database_now(db),
                    User.is_active.is_(False), User.username.is_(None), User.password_hash.is_(None), User.role != "administrator",
                    SolveSession.trace_expires_at.is_(None), SolveSession.trace_purged_at.is_not(None),
                    SolveSession.trace_expires_at <= database_now(db),
                    and_(JudgeJob.state == "RUNNING", JudgeAttempt.lease_expires_at <= database_now(db))))
                .order_by(JudgeJob.created_at, JudgeJob.id).limit(limit)))
        for job_id in ids:
            with self.factory.begin() as db:
                try:
                    owner, session, submission, job, attempt = self._locked(db, job_id, skip_locked=True)
                except JudgeError:
                    continue
                now = database_now(db)
                if job.state not in ACTIVE_STATES:
                    continue
                code = ("account_unavailable" if not owner.is_active or not owner.username or not owner.password_hash or owner.role != "administrator"
                    else "trace_expired" if trace_expired(session, now) else "job_timeout" if aware(job.deadline_at) <= now
                    else "lease_expired" if attempt is not None and aware(attempt.lease_expires_at) <= now else None)
                if code:
                    self._finish(db, job, attempt, "FAILED", code)
                    recovered += 1
        return recovered


def expire_session_jobs(db, session_id, now=None):
    """Caller holds the solve-session lock; only acquire its Judge descendants.

    Retention already owns the session, so this helper must not acquire a User
    lock in reverse order. Audit metadata survives without copying Trace content.
    """
    now = now or database_now(db)
    jobs = list(db.scalars(select(JudgeJob).where(JudgeJob.session_id == session_id,
        JudgeJob.state.in_(ACTIVE_STATES)).order_by(JudgeJob.id).with_for_update()))
    for job in jobs:
        attempt = db.scalar(select(JudgeAttempt).where(JudgeAttempt.job_id == job.id)
            .with_for_update().execution_options(populate_existing=True))
        job.state, job.error_code, job.finished_at = "FAILED", "trace_expired", now
        job.fence += 1
        job.reservation_active = False
        if attempt is not None:
            attempt.revoked_at = now
        audit(db, "judge_terminal", actor_id=job.owner_id, resource_id=job.id,
            state="FAILED", code="trace_expired", provenance="synthetic_mock")
    return len(jobs)
