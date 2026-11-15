"""M6-A lifecycle/retention boundaries; PostgreSQL-only rows test real lock races."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from threading import Barrier
from time import sleep
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import func, select, text

from praxioj.execution import MockJudgeBackend
from praxioj_api.jobs import aware, database_now
from praxioj_api.judge import JudgeBroker, JudgeError, METADATA_LIMIT_MULTIPLIER
from praxioj_api.judge_models import JudgeAttempt, JudgeJob, judge_public
from praxioj_api.judge_routes import dispatch_mock
from praxioj_api.maintenance import run_maintenance
from praxioj_api.models import Evaluation, SolveSession, User
from praxioj_api.retention_models import AuditRecord
from praxioj_api.settings import Settings
from test_judge_broker import enqueue, raw_for, setup_judge
from conftest import ROOT


def complete_fixture(app, fixture):
    job = enqueue(app, fixture)
    lease = fixture[0].claim("lifecycle-worker", job.id)
    fixture[0].complete(lease, raw_for(lease))
    return job, lease


def age_job(app, job_id, days):
    with app.state.session_factory.begin() as db:
        db.get(JudgeJob, job_id).finished_at = database_now(db) - timedelta(days=days)


def postgres_only(app):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for authoritative-clock and row-lock races")


def test_renewal_ack_is_server_observed_and_bounded_by_capability(app, setup_judge):
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker", job.id)
    with app.state.session_factory.begin() as db:
        attempt = db.get(JudgeAttempt, lease.attempt_id)
        attempt.expires_at = database_now(db) + timedelta(seconds=2)
    ack = broker.renew(lease)
    assert ack is not None and ack.attempt_id == lease.attempt_id and ack.fence == lease.fence
    assert ack.heartbeat_at < ack.lease_expires_at <= ack.expires_at <= ack.deadline_at
    assert lease.token not in repr(ack)
    with app.state.session_factory() as db:
        attempt = db.get(JudgeAttempt, lease.attempt_id)
        assert aware(attempt.heartbeat_at) == ack.heartbeat_at
        assert aware(attempt.lease_expires_at) == ack.lease_expires_at


@pytest.mark.parametrize("change", [{"worker_id": "wrong-worker"}, {"fence": 999},
    {"token": "wrong-capability"}, {"attempt_id": str(uuid4())}])
def test_unauthorized_heartbeat_does_not_extend_or_cancel_current_attempt(app, setup_judge, change):
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker", job.id)
    with app.state.session_factory() as db:
        before = db.get(JudgeAttempt, lease.attempt_id).lease_expires_at
    assert broker.renew(replace(lease, **change)) is None
    with app.state.session_factory() as db:
        assert db.get(JudgeAttempt, lease.attempt_id).lease_expires_at == before
        assert db.get(JudgeJob, job.id).state == "RUNNING"
    assert broker.heartbeat(lease)


@pytest.mark.parametrize("field", ["expires_at", "lease_expires_at", "deadline_at"])
def test_expired_authority_cannot_be_resurrected_and_releases_reservation(app, setup_judge, field):
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker", job.id)
    raw = raw_for(lease)
    with app.state.session_factory.begin() as db:
        past = database_now(db) - timedelta(seconds=1)
        target = db.get(JudgeJob, job.id) if field == "deadline_at" else db.get(JudgeAttempt, lease.attempt_id)
        setattr(target, field, past)
    assert broker.renew(lease) is None
    assert broker.renew(lease) is None
    with pytest.raises(JudgeError, match="attempt_not_current"):
        broker.complete(lease, raw)
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, job.id).state == "FAILED"
        assert not db.get(JudgeJob, job.id).reservation_active
        assert db.get(JudgeAttempt, lease.attempt_id).revoked_at is not None


def test_policy_drift_during_renewal_fails_closed(app, setup_judge):
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker", job.id)
    with app.state.session_factory.begin() as db:
        stored = db.get(JudgeJob, job.id)
        stored.spec = {**stored.spec, "unexpected_policy": "changed"}
    assert broker.renew(lease) is None
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, job.id).error_code == "request_snapshot_changed"
        assert not db.get(JudgeJob, job.id).reservation_active


@pytest.mark.parametrize("phase", ["renewal", "completion", "renewal_trace", "completion_trace"])
def test_expiry_during_validation_cannot_extend_or_accept_authority(app, setup_judge, monkeypatch, phase):
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker", job.id)
    raw = raw_for(lease)
    calls = []
    with app.state.session_factory.begin() as db:
        if phase.endswith("_trace"):
            db.get(SolveSession, setup_judge[2]).trace_expires_at = database_now(db) + timedelta(seconds=1)
        else:
            db.get(JudgeAttempt, lease.attempt_id).expires_at = database_now(db) + timedelta(seconds=1)
    if phase.startswith("renewal"):
        original = broker._binding
        def delayed(*args, **kwargs):
            result = original(*args, **kwargs)
            calls.append(True)
            sleep(1.1)
            return result
        monkeypatch.setattr(broker, "_binding", delayed)
        assert broker.renew(lease) is None
    else:
        import praxioj_api.judge as judge_module
        original = judge_module.validate_and_assess_synthetic_execution
        def delayed(*args):
            result = original(*args)
            calls.append(True)
            sleep(1.1)
            return result
        monkeypatch.setattr(judge_module, "validate_and_assess_synthetic_execution", delayed)
        with pytest.raises(JudgeError, match="trace_expired" if phase.endswith("_trace") else "execution_authority_expired"):
            broker.complete(lease, raw)
    assert calls == [True]
    with app.state.session_factory() as db:
        stored = db.get(JudgeJob, job.id)
        assert stored.state == "FAILED" and stored.result is None and stored.assessment is None
        assert not stored.reservation_active
        assert db.get(JudgeAttempt, lease.attempt_id).consumed_at is None


@pytest.mark.postgres
def test_postgres_renewal_uses_database_clock_not_worker_clock(app, setup_judge, monkeypatch):
    postgres_only(app)
    job = enqueue(app, setup_judge)
    lease = setup_judge[0].claim("worker", job.id)
    with app.state.session_factory() as db:
        before = database_now(db)
    monkeypatch.setattr("praxioj_api.jobs.utcnow", lambda: datetime(2100, 1, 1, tzinfo=timezone.utc))
    ack = setup_judge[0].renew(lease)
    with app.state.session_factory() as db:
        after = database_now(db)
    assert before <= ack.heartbeat_at <= after


@pytest.mark.postgres
def test_heartbeat_cancellation_race_cannot_revive_attempt(app, setup_judge):
    postgres_only(app)
    broker, owner_id, *_ = setup_judge
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker", job.id)
    barrier = Barrier(2)
    def heartbeat():
        barrier.wait()
        return broker.heartbeat(lease)
    def cancel():
        barrier.wait()
        with app.state.session_factory.begin() as db:
            return broker.cancel(db, db.get(User, owner_id), job.id).state
    with ThreadPoolExecutor(max_workers=2) as pool:
        renewed, cancelled = pool.submit(heartbeat), pool.submit(cancel)
        assert renewed.result() in (True, False)
        assert cancelled.result() == "CANCELLED"
    assert broker.heartbeat(lease) is False
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, job.id).state == "CANCELLED"
        assert db.get(JudgeAttempt, lease.attempt_id).revoked_at is not None


@pytest.mark.postgres
def test_expired_heartbeat_recovery_race_has_one_terminal_transition(app, setup_judge):
    postgres_only(app)
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker", job.id)
    with app.state.session_factory.begin() as db:
        db.get(JudgeAttempt, lease.attempt_id).lease_expires_at = database_now(db) - timedelta(seconds=1)
    barrier = Barrier(2)
    def heartbeat():
        barrier.wait()
        return broker.heartbeat(lease)
    def recover():
        barrier.wait()
        return broker.recover()
    with ThreadPoolExecutor(max_workers=2) as pool:
        one, two = pool.submit(heartbeat), pool.submit(recover)
        assert one.result() is False
        assert two.result() in (0, 1)
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, job.id).state == "FAILED"
        assert db.scalar(select(func.count()).select_from(AuditRecord)
            .where(AuditRecord.action == "judge_terminal", AuditRecord.resource_id == job.id)) == 1


def test_dispatch_renews_delayed_mock_and_stops_heartbeat_before_completion(app, setup_judge, monkeypatch):
    broker = JudgeBroker(app.state.session_factory, replace(setup_judge[0].settings, judge_lease_seconds=1))
    fixture = (broker, *setup_judge[1:])
    job = enqueue(app, fixture)
    calls = []
    original = broker.heartbeat
    def heartbeat(lease):
        calls.append(lease.attempt_id)
        return original(lease)
    monkeypatch.setattr(broker, "heartbeat", heartbeat)
    class DelayedMock:
        async def execute(self, request):
            await asyncio.sleep(1.6)
            return await MockJudgeBackend().execute(request)
    async def exercise():
        result = await dispatch_mock(broker, DelayedMock(), job.id)
        count = len(calls)
        await asyncio.sleep(0.4)
        assert len(calls) == count
        return result
    assert asyncio.run(exercise())["state"] == "COMPLETED"
    assert len(calls) >= 3


def test_dispatch_cancels_backend_when_authority_is_lost(app, setup_judge, monkeypatch):
    broker = JudgeBroker(app.state.session_factory, replace(setup_judge[0].settings, judge_lease_seconds=1))
    job = enqueue(app, (broker, *setup_judge[1:]))
    stopped = []
    class WaitingMock:
        async def execute(self, _request):
            try:
                await asyncio.sleep(10)
            finally:
                stopped.append(True)
    monkeypatch.setattr(broker, "heartbeat", lambda _lease: False)
    with pytest.raises(JudgeError, match="execution_authority_lost"):
        asyncio.run(dispatch_mock(broker, WaitingMock(), job.id))
    assert stopped == [True]
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, job.id).state == "FAILED"
        assert not db.get(JudgeJob, job.id).reservation_active


def test_dispatch_request_cancellation_stops_renewal_and_backend(app, setup_judge, monkeypatch):
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    started = asyncio.Event()
    stopped = []
    calls = []
    class WaitingMock:
        async def execute(self, _request):
            started.set()
            try:
                await asyncio.sleep(10)
            finally:
                stopped.append(True)
    monkeypatch.setattr(broker, "heartbeat", lambda _lease: calls.append(True) or True)
    async def exercise():
        task = asyncio.create_task(dispatch_mock(broker, WaitingMock(), job.id))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    asyncio.run(exercise())
    assert stopped == [True] and calls == []
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, job.id).error_code == "worker_stopped"


def test_dispatch_timeout_stops_backend_and_releases_capacity(app, setup_judge, monkeypatch):
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    stopped = []
    class WaitingMock:
        async def execute(self, _request):
            try:
                await asyncio.sleep(10)
            finally:
                stopped.append(True)
    monkeypatch.setattr("praxioj_api.judge_routes.DISPATCH_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(JudgeError, match="backend_error"):
        asyncio.run(dispatch_mock(broker, WaitingMock(), job.id))
    assert stopped == [True]
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, job.id).error_code == "backend_timeout"
        assert not db.get(JudgeJob, job.id).reservation_active


def test_cancellation_confirmation_requires_original_live_bound_authority(app, setup_judge):
    broker, owner_id, *_ = setup_judge
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker", job.id)
    assert broker.cancelled(lease) is False
    with app.state.session_factory.begin() as db:
        broker.cancel(db, db.get(User, owner_id), job.id)
    assert broker.cancelled(lease) is True
    for change in ({"token": "wrong-capability"}, {"worker_id": "another-worker"}, {"fence": 99}):
        assert broker.cancelled(replace(lease, **change)) is False
    assert broker.renew(lease) is None
    with app.state.session_factory.begin() as db:
        db.get(JudgeAttempt, lease.attempt_id).expires_at = database_now(db) - timedelta(seconds=1)
    assert broker.cancelled(lease) is False


def test_retention_preserves_score_but_marks_removed_evidence_and_is_idempotent(app, setup_judge):
    broker, _, sid, submission_id = setup_judge
    job, lease = complete_fixture(app, setup_judge)
    with app.state.session_factory() as db:
        original = db.scalar(select(Evaluation).where(Evaluation.submission_id == submission_id)).result
        checkpoint = db.get(SolveSession, sid).trace_head_sha256
    assert broker.purge_history()["purged_judge_payloads"] == 0
    age_job(app, job.id, 8)
    counts = broker.purge_history()
    assert counts["purged_judge_payloads"] == 1 and counts["deleted_judge_attempts"] == 1
    with app.state.session_factory() as db:
        stored = db.get(JudgeJob, job.id)
        public = judge_public(stored)
        assert stored.result is None and stored.spec == {} and stored.evidence_purged_at is not None
        assert public["evidence_status"] == public["assessment"]["evidence_status"] == "unavailable"
        assert public["assessment"]["evaluation"]["score"] == 100
        assert db.get(JudgeAttempt, lease.attempt_id) is None
        assert db.scalar(select(Evaluation).where(Evaluation.submission_id == submission_id)).result == original
        assert db.get(SolveSession, sid).trace_head_sha256 == checkpoint
    assert not any(broker.purge_history().values())
    assert enqueue(app, setup_judge, job.request_id).id == job.id
    assert broker.claim("worker", job.id) is None
    assert broker.heartbeat(lease) is False


def test_retention_hard_deletes_only_after_metadata_policy_and_reconciles_quota(app, setup_judge):
    broker = setup_judge[0]
    job, _ = complete_fixture(app, setup_judge)
    age_job(app, job.id, 8)
    with app.state.session_factory.begin() as db:
        db.get(JudgeJob, job.id).reservation_active = True
    assert broker.purge_history()["reconciled_judge_reservations"] == 1
    age_job(app, job.id, 31)
    counts = broker.purge_history()
    assert counts["deleted_judge_jobs"] == 1
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, job.id) is None
        assert db.scalar(select(func.count()).select_from(AuditRecord)
            .where(AuditRecord.action == "judge_history_deleted", AuditRecord.resource_id == job.id)) == 1
    assert not any(broker.purge_history().values())


def test_hard_delete_ends_idempotency_window_without_reviving_old_job_authority(app, setup_judge):
    broker = setup_judge[0]
    job, lease = complete_fixture(app, setup_judge)
    raw = raw_for(lease)
    age_job(app, job.id, 31)
    assert broker.purge_history()["deleted_judge_jobs"] == 1
    replacement = enqueue(app, setup_judge, job.request_id)
    assert replacement.id != job.id and replacement.request_id == job.request_id
    with pytest.raises(JudgeError, match="resource_not_found"):
        broker.complete(lease, raw)
    assert broker.heartbeat(lease) is False
    assert replacement.state == "PENDING"


def test_retention_skips_active_jobs_and_anomalous_unrevoked_authority(app, setup_judge):
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker", job.id)
    with app.state.session_factory.begin() as db:
        db.get(JudgeJob, job.id).finished_at = database_now(db) - timedelta(days=31)
    assert not any(broker.purge_history().values())
    with app.state.session_factory.begin() as db:
        db.get(JudgeJob, job.id).state = "FAILED"
    assert not any(broker.purge_history().values())
    with app.state.session_factory.begin() as db:
        db.get(JudgeAttempt, lease.attempt_id).expires_at = database_now(db) - timedelta(seconds=1)
    assert broker.purge_history()["deleted_judge_jobs"] == 1


def test_payload_cleanup_recovers_retained_capacity_but_bounds_metadata(app, setup_judge):
    broker = JudgeBroker(app.state.session_factory, replace(setup_judge[0].settings,
        judge_account_retained_jobs=1, judge_system_retained_jobs=1))
    fixture = (broker, *setup_judge[1:])
    for _ in range(METADATA_LIMIT_MULTIPLIER):
        job, _ = complete_fixture(app, fixture)
        with pytest.raises(JudgeError, match="judge_capacity_exceeded"):
            enqueue(app, fixture)
        age_job(app, job.id, 8)
        assert broker.purge_history()["purged_judge_payloads"] == 1
    with pytest.raises(JudgeError, match="judge_capacity_exceeded"):
        enqueue(app, fixture)
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(JudgeJob)) == METADATA_LIMIT_MULTIPLIER
        assert db.scalar(select(func.count()).select_from(JudgeJob)
            .where(JudgeJob.reservation_active.is_(True))) == 0
    age_job(app, job.id, 31)
    assert broker.purge_history()["deleted_judge_jobs"] == 1
    assert enqueue(app, fixture).state == "PENDING"


def test_standalone_maintenance_purges_history_even_when_runtime_unavailable(app, setup_judge):
    job, _ = complete_fixture(app, setup_judge)
    age_job(app, job.id, 8)
    result = run_maintenance(app.state.session_factory, app.state.settings)
    assert app.state.settings.judge_backend == "unavailable"
    assert result["purged_judge_payloads"] == 1


@pytest.mark.postgres
def test_concurrent_cleanup_is_idempotent_and_never_purges_running_result(app, setup_judge):
    postgres_only(app)
    broker = setup_judge[0]
    old, _ = complete_fixture(app, setup_judge)
    age_job(app, old.id, 8)
    active = enqueue(app, setup_judge)
    lease = broker.claim("worker", active.id)
    raw = raw_for(lease)
    barrier = Barrier(3)
    def cleanup():
        barrier.wait()
        return broker.purge_history()
    def complete():
        barrier.wait()
        return broker.complete(lease, raw)
    with ThreadPoolExecutor(max_workers=3) as pool:
        one, two, three = pool.submit(cleanup), pool.submit(cleanup), pool.submit(complete)
        totals = one.result()["purged_judge_payloads"] + two.result()["purged_judge_payloads"]
        assert three.result()["state"] == "COMPLETED"
    # SKIP LOCKED may defer the old row while completion owns the account.
    totals += broker.purge_history()["purged_judge_payloads"]
    assert totals == 1
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, active.id).result is not None
        assert db.get(JudgeJob, active.id).evidence_purged_at is None


def test_cleanup_is_bounded_and_restore_quarantine_blocks_it(app, setup_judge):
    broker = setup_judge[0]
    for _ in range(2):
        job, _ = complete_fixture(app, setup_judge)
        age_job(app, job.id, 8)
    assert broker.purge_history(limit=1)["purged_judge_payloads"] == 1
    with app.state.session_factory.begin() as db:
        db.execute(text("CREATE TABLE praxioj_restore_quarantine (id INTEGER)"))
    with pytest.raises(RuntimeError, match="quarantined"):
        broker.purge_history()


@pytest.mark.postgres
def test_concurrent_heartbeats_serialize_and_preserve_latest_db_ack(app, setup_judge):
    postgres_only(app)
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker", job.id)
    barrier = Barrier(2)
    def renew(_):
        barrier.wait()
        return broker.renew(lease)
    with ThreadPoolExecutor(max_workers=2) as pool:
        acknowledgements = list(pool.map(renew, range(2)))
    assert all(ack is not None for ack in acknowledgements)
    with app.state.session_factory() as db:
        stored = db.get(JudgeAttempt, lease.attempt_id)
        assert aware(stored.heartbeat_at) == max(ack.heartbeat_at for ack in acknowledgements)
        assert aware(stored.lease_expires_at) == max(ack.lease_expires_at for ack in acknowledgements)


@pytest.mark.postgres
def test_cleanup_and_admission_race_does_not_double_reserve_capacity(app, setup_judge):
    postgres_only(app)
    broker = JudgeBroker(app.state.session_factory, replace(setup_judge[0].settings,
        judge_account_retained_jobs=1, judge_system_retained_jobs=1))
    fixture = (broker, *setup_judge[1:])
    job, _ = complete_fixture(app, fixture)
    age_job(app, job.id, 8)
    barrier = Barrier(2)
    def cleanup():
        barrier.wait()
        return broker.purge_history()
    def admit():
        barrier.wait()
        try:
            return enqueue(app, fixture).id
        except JudgeError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        one, two = pool.submit(cleanup), pool.submit(admit)
        one.result()
        admitted = two.result()
    broker.purge_history()
    if admitted == "judge_capacity_exceeded":
        admitted = enqueue(app, fixture).id
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, admitted).state == "PENDING"
        assert db.scalar(select(func.count()).select_from(JudgeJob)
            .where(JudgeJob.reservation_active.is_(True))) == 1


@pytest.mark.parametrize("days", [(0, 30), (7, 6), (7, 91), (True, 30), (1, 1.5)])
def test_retention_settings_are_bounded_integer_days(days):
    with pytest.raises(ValueError, match="Judge retention"):
        Settings(judge_result_retention_days=days[0], judge_metadata_retention_days=days[1])


def test_m5_upgrade_keeps_existing_judge_assessment_and_trace(app, setup_judge):
    job, lease = complete_fixture(app, setup_judge)
    with app.state.session_factory() as db:
        result = db.get(JudgeJob, job.id).result
        checkpoint = db.get(SolveSession, setup_judge[2]).trace_head_sha256
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    command.downgrade(config, "0008_judge_execution")
    command.upgrade(config, "head")
    with app.state.session_factory() as db:
        stored = db.get(JudgeJob, job.id)
        assert stored.result == result and stored.evidence_purged_at is None
        assert db.get(JudgeAttempt, lease.attempt_id).consumed_at is not None
        assert db.get(SolveSession, setup_judge[2]).trace_head_sha256 == checkpoint
