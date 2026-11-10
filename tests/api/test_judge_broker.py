"""M5 synthetic broker authority, lifecycle and PostgreSQL race invariants."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import json
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from praxioj.execution import FIXTURE_SUBMISSION_CONTENT, MOCK_FIXTURE_ID, MockJudgeBackend
from praxioj_api.judge import JudgeBroker, JudgeError, RESULT_RESERVATION_BYTES, expire_session_jobs
from praxioj_api.judge_models import JudgeAttempt, JudgeJob, judge_public
from praxioj_api.models import Evaluation, SolveSession, Submission, User, utcnow
from praxioj_api.retention_models import AuditRecord
from conftest import authenticate_client, ROOT


@pytest.fixture
def setup_judge(app, client):
    owner_id = client.get("/api/auth/me").json()["user"]["id"]
    session = client.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"}).json()
    response = client.post(f"/api/sessions/{session['id']}/submissions", json={"content": FIXTURE_SUBMISSION_CONTENT})
    assert response.status_code == 201, response.text
    submission_id = response.json()["submission_id"]
    with app.state.session_factory.begin() as db:
        db.get(User, owner_id).role = "administrator"
    broker = JudgeBroker(app.state.session_factory, replace(app.state.settings, judge_backend="mock"))
    return broker, owner_id, session["id"], submission_id


def enqueue(app, fixture, request_id=None):
    broker, owner_id, _, submission_id = fixture
    with app.state.session_factory.begin() as db:
        return broker.enqueue(db, db.get(User, owner_id), submission_id, request_id or str(uuid4()), MOCK_FIXTURE_ID)


def raw_for(lease, scenario="success"):
    return asyncio.run(MockJudgeBackend(scenario=scenario).execute(lease.request))


def test_synthetic_completion_is_separate_from_original_evaluation(app, setup_judge):
    broker, _, sid, submission_id = setup_judge
    with app.state.session_factory() as db:
        original = db.scalar(select(Evaluation).where(Evaluation.submission_id == submission_id)).result
        checkpoint = db.get(SolveSession, sid).trace_head_sha256
    job = enqueue(app, setup_judge)
    lease = broker.claim("synthetic-worker")
    assert lease is not None and lease.job_id == job.id
    assert broker.heartbeat(lease)
    assert lease.token not in repr(lease)
    with app.state.session_factory() as db:
        attempt = db.get(JudgeAttempt, lease.attempt_id)
        assert attempt.capability_hash != lease.token and len(attempt.capability_hash) == 64
        assert lease.token not in json.dumps(db.get(JudgeJob, job.id).spec)
    result = broker.complete(lease, raw_for(lease))
    assert result["state"] == "COMPLETED" and result["provenance"] == "synthetic_mock"
    assert result["assessment"]["independent_execution_evidence"] is False
    assert result["assessment"]["evaluation"]["score"] == 100
    assert "worker_id" not in json.dumps(result, default=str) and lease.token not in json.dumps(result, default=str)
    with app.state.session_factory() as db:
        assert db.scalar(select(Evaluation).where(Evaluation.submission_id == submission_id)).result == original
        assert db.get(SolveSession, sid).trace_head_sha256 == checkpoint
        assert not db.get(JudgeJob, job.id).reservation_active
        assert db.get(JudgeAttempt, lease.attempt_id).consumed_at is not None
        assert lease.token not in json.dumps([row.details for row in db.scalars(select(AuditRecord))])


def test_default_runtime_unavailable_and_idempotent_request_binding(app, setup_judge):
    broker, owner_id, _, submission_id = setup_judge
    request_id = str(uuid4())
    unavailable = JudgeBroker(app.state.session_factory, replace(app.state.settings, judge_backend="unavailable"))
    with app.state.session_factory.begin() as db, pytest.raises(JudgeError, match="runtime_unavailable"):
        unavailable.enqueue(db, db.get(User, owner_id), submission_id, request_id, MOCK_FIXTURE_ID)
    first = enqueue(app, setup_judge, request_id)
    second = enqueue(app, setup_judge, request_id)
    assert first.id == second.id
    with app.state.session_factory.begin() as db, pytest.raises(JudgeError, match="idempotency_conflict"):
        broker.enqueue(db, db.get(User, owner_id), submission_id, request_id, "wrong-fixture")
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(JudgeJob)) == 1


@pytest.mark.parametrize("change,code", [
    ({"token": "invalid-token"}, "capability_invalid"),
    ({"attempt_id": str(uuid4())}, "attempt_not_current"),
    ({"fence": 999}, "attempt_not_current"),
    ({"worker_id": "another-worker"}, "attempt_not_current"),
])
def test_capability_cannot_change_attempt_fence_worker_or_token(app, setup_judge, change, code):
    job = enqueue(app, setup_judge)
    broker = setup_judge[0]
    lease = broker.claim("trusted-worker")
    with pytest.raises(JudgeError, match=code):
        broker.complete(replace(lease, **change), raw_for(lease))
    assert broker.complete(lease, raw_for(lease))["state"] == "COMPLETED"
    with pytest.raises(JudgeError, match="attempt_not_current"):
        broker.complete(lease, raw_for(lease))
    with app.state.session_factory() as db:
        assert not db.get(JudgeJob, job.id).reservation_active


@pytest.mark.parametrize("audience,operation", [("wrong-audience", "submit_result"), ("mock-judge", "read_secret")])
def test_wrong_capability_audience_or_operation_does_not_consume_valid_authority(app, setup_judge, audience, operation):
    enqueue(app, setup_judge)
    broker = setup_judge[0]
    lease = broker.claim("worker")
    with pytest.raises(JudgeError, match="capability_invalid"):
        broker.complete(lease, raw_for(lease), audience=audience, operation=operation)
    assert broker.complete(lease, raw_for(lease))["state"] == "COMPLETED"


def test_capability_from_another_job_cannot_deliver_or_cancel_its_result(app, setup_judge):
    broker = setup_judge[0]
    first, second = enqueue(app, setup_judge), enqueue(app, setup_judge)
    one, two = broker.claim("worker-one", first.id), broker.claim("worker-two", second.id)
    forged = replace(one, job_id=two.job_id, attempt_id=two.attempt_id, fence=two.fence, worker_id=two.worker_id)
    with pytest.raises(JudgeError, match="capability_invalid"):
        broker.complete(forged, raw_for(two))
    assert broker.complete(one, raw_for(one))["state"] == "COMPLETED"
    assert broker.complete(two, raw_for(two))["state"] == "COMPLETED"


@pytest.mark.parametrize("field", ["input_digest", "policy_digest", "request_digest", "runtime_image_digest"])
def test_result_binding_digests_are_validated_before_any_assessment_is_stored(app, setup_judge, field):
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker")
    raw = raw_for(lease)
    raw[field] = "0" * 64
    result = broker.complete(lease, raw)
    assert result["state"] == "FAILED" and result["error_code"] == "invalid_result"
    assert result["assessment"] is None and result["result"] is None
    with app.state.session_factory() as db:
        assert not db.get(JudgeJob, job.id).reservation_active


@pytest.mark.parametrize("scenario,state", [("evaluation_failed", "COMPLETED"), ("failure", "FAILED"),
    ("cancelled", "CANCELLED"), ("timeout", "FAILED"), ("malformed", "FAILED"),
    ("oversized", "FAILED"), ("bad_digest", "FAILED")])
def test_mock_failures_and_invalid_results_never_replace_original_evaluation(app, setup_judge, scenario, state):
    broker, _, _, submission_id = setup_judge
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker")
    result = broker.complete(lease, raw_for(lease, scenario))
    assert result["state"] == state
    if scenario == "evaluation_failed":
        assert result["assessment"]["evaluation"]["score"] == 0
    if scenario in {"malformed", "oversized", "bad_digest"}:
        assert result["error_code"] == "invalid_result" and result["assessment"] is None and result["result"] is None
    with app.state.session_factory() as db:
        assert db.scalar(select(Evaluation).where(Evaluation.submission_id == submission_id)).result["score"] == 100
        assert not db.get(JudgeJob, job.id).reservation_active


def test_cancel_is_durable_and_invalidates_late_completion(app, setup_judge):
    broker, owner_id, _, _ = setup_judge
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker")
    raw = raw_for(lease)
    with app.state.session_factory.begin() as db:
        assert broker.cancel(db, db.get(User, owner_id), job.id).state == "CANCELLED"
    with pytest.raises(JudgeError, match="attempt_not_current"):
        broker.complete(lease, raw)
    assert not broker.heartbeat(lease)


@pytest.mark.parametrize("complete_first", [False, True])
def test_expired_capability_and_lease_fail_without_replay(app, setup_judge, complete_first):
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker")
    with app.state.session_factory.begin() as db:
        db.get(JudgeAttempt, lease.attempt_id).expires_at = utcnow() - timedelta(seconds=1)
        db.get(JudgeAttempt, lease.attempt_id).lease_expires_at = utcnow() - timedelta(seconds=1)
    if complete_first:
        with pytest.raises(JudgeError, match="execution_authority_expired"):
            broker.complete(lease, raw_for(lease))
    assert broker.recover() == (0 if complete_first else 1)
    assert broker.recover() == 0
    assert broker.claim("new-worker") is None
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, job.id).state == "FAILED"
        assert not db.get(JudgeJob, job.id).reservation_active


@pytest.mark.parametrize("mutate", ["submission", "policy", "request_digest", "trace_expiry", "role"])
def test_current_binding_is_rechecked_before_result_acceptance(app, setup_judge, mutate):
    broker, owner_id, sid, submission_id = setup_judge
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker")
    raw = raw_for(lease)
    with app.state.session_factory.begin() as db:
        if mutate == "submission":
            db.get(Submission, submission_id).content_sha256 = "0" * 64
        elif mutate == "policy":
            row = db.get(JudgeJob, job.id)
            row.spec = {**row.spec, "submitted_artifacts": [] if row.spec["submitted_artifacts"] else [{"invalid": "metadata"}]}
        elif mutate == "request_digest":
            db.get(JudgeAttempt, lease.attempt_id).request_digest = "0" * 64
        elif mutate == "trace_expiry":
            db.get(SolveSession, sid).trace_expires_at = utcnow() - timedelta(seconds=1)
        else:
            db.get(User, owner_id).role = "participant"
    with pytest.raises(JudgeError):
        broker.complete(lease, raw)
    if mutate == "role":
        assert broker.recover() == 1
    with app.state.session_factory() as db:
        stored = db.get(JudgeJob, job.id)
        assert stored.result is None and stored.state == "FAILED" and not stored.reservation_active


def test_expiry_suffix_helper_revokes_active_jobs_and_is_repeatable(app, setup_judge):
    broker, _, sid, _ = setup_judge
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker")
    with app.state.session_factory.begin() as db:
        db.scalar(select(SolveSession).where(SolveSession.id == sid).with_for_update())
        assert expire_session_jobs(db, sid) == 1
        assert expire_session_jobs(db, sid) == 0
    with pytest.raises(JudgeError):
        broker.complete(lease, raw_for(lease))
    with app.state.session_factory() as db:
        row = db.get(JudgeJob, job.id)
        assert row.error_code == "trace_expired" and not row.reservation_active


def test_capacity_reservations_release_once_and_retained_cap_remains(app, setup_judge):
    original = setup_judge[0]
    settings = replace(original.settings, judge_account_active_jobs=1, judge_account_retained_jobs=2,
        judge_account_reserved_output_bytes=RESULT_RESERVATION_BYTES)
    broker = JudgeBroker(app.state.session_factory, settings)
    fixture = (broker, *setup_judge[1:])
    first = enqueue(app, fixture)
    with pytest.raises(JudgeError, match="judge_capacity_exceeded"):
        enqueue(app, fixture)
    with app.state.session_factory.begin() as db:
        broker.cancel(db, db.get(User, fixture[1]), first.id)
    second = enqueue(app, fixture)
    with app.state.session_factory.begin() as db:
        broker.cancel(db, db.get(User, fixture[1]), second.id)
    with pytest.raises(JudgeError, match="judge_capacity_exceeded"):
        enqueue(app, fixture)
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(JudgeJob).where(JudgeJob.reservation_active.is_(True))) == 0


def test_backend_error_and_transaction_rollback_preserve_consistent_slots(app, setup_judge):
    broker = setup_judge[0]
    with app.state.session_factory.begin() as db:
        owner = db.get(User, setup_judge[1])
        try:
            with db.begin_nested():
                broker.enqueue(db, owner, setup_judge[3], str(uuid4()), MOCK_FIXTURE_ID)
                raise RuntimeError("controlled rollback")
        except RuntimeError:
            pass
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(JudgeJob)) == 0
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker")
    assert broker.fail(lease, "private-raw-detail")
    assert not broker.fail(lease)
    with app.state.session_factory() as db:
        row = db.get(JudgeJob, job.id)
        assert row.error_code == "backend_error" and not row.reservation_active


@pytest.mark.postgres
def test_concurrent_claim_and_duplicate_completion_are_single_winner(app, setup_judge):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for Judge row-lock races")
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    barrier = Barrier(2)
    def claim(worker):
        barrier.wait()
        return broker.claim(worker, job.id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(claim, ["worker-a", "worker-b"]))
    winners = [lease for lease in leases if lease]
    assert len(winners) == 1
    lease = winners[0]
    raw = raw_for(lease)
    barrier = Barrier(2)
    def complete(_):
        barrier.wait()
        try:
            return broker.complete(lease, raw)["state"]
        except JudgeError:
            return "rejected"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(complete, range(2))) == ["COMPLETED", "rejected"]


@pytest.mark.postgres
def test_cancel_completion_race_has_one_terminal_decision(app, setup_judge):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for Judge cancellation/result race")
    broker, owner_id, _, _ = setup_judge
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker")
    raw = raw_for(lease)
    barrier = Barrier(2)
    def cancel():
        barrier.wait()
        with app.state.session_factory.begin() as db:
            return broker.cancel(db, db.get(User, owner_id), job.id).state
    def complete():
        barrier.wait()
        try:
            return broker.complete(lease, raw)["state"]
        except JudgeError:
            return "rejected"
    with ThreadPoolExecutor(max_workers=2) as pool:
        one, two = pool.submit(cancel), pool.submit(complete)
        states = [one.result(), two.result()]
    with app.state.session_factory() as db:
        stored = db.get(JudgeJob, job.id)
        assert stored.state in {"COMPLETED", "CANCELLED"} and not stored.reservation_active
        assert (stored.result is not None) == (stored.state == "COMPLETED")
    assert "CANCELLED" in states or states == ["COMPLETED", "COMPLETED"]


def test_broker_recreation_preserves_request_and_original_policy(app, setup_judge):
    broker, *_ = setup_judge
    job = enqueue(app, setup_judge)
    lease = broker.claim("worker")
    replacement = JudgeBroker(app.state.session_factory, broker.settings)
    assert replacement.complete(lease, raw_for(lease))["state"] == "COMPLETED"
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, job.id).spec["request_template"]["policy"] == lease.request.policy.model_dump(mode="json")


@pytest.mark.postgres
def test_concurrent_idempotency_and_global_capacity_reservation(app, setup_judge):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for Judge admission races")
    broker = setup_judge[0]
    request_id = str(uuid4())
    barrier = Barrier(2)
    def same_request(_):
        barrier.wait()
        return enqueue(app, setup_judge, request_id).id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(same_request, range(2)))
    assert ids[0] == ids[1]
    with app.state.session_factory.begin() as db:
        broker.cancel(db, db.get(User, setup_judge[1]), ids[0])
    # Separate owners bypass the per-owner row lock; the shared admission gate
    # must independently serialize the global queue and output reservation.
    with TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as other:
        identity = authenticate_client(other)
        sid = other.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"}).json()["id"]
        sub = other.post(f"/api/sessions/{sid}/submissions", json={"content": FIXTURE_SUBMISSION_CONTENT}).json()["submission_id"]
        with app.state.session_factory.begin() as db:
            db.get(User, identity["user"]["id"]).role = "administrator"
    limited = JudgeBroker(app.state.session_factory, replace(broker.settings, judge_max_pending=1,
        judge_system_reserved_output_bytes=RESULT_RESERVATION_BYTES))
    fixtures = [(limited, *setup_judge[1:]), (limited, identity["user"]["id"], sid, sub)]
    barrier = Barrier(2)
    def compete(fixture):
        barrier.wait()
        try:
            return enqueue(app, fixture).id
        except JudgeError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(compete, fixtures))
    assert outcomes.count("judge_capacity_exceeded") == 1
    with app.state.session_factory() as db:
        assert db.scalar(select(func.sum(JudgeJob.reserved_output_bytes)).where(JudgeJob.reservation_active.is_(True))) == RESULT_RESERVATION_BYTES


def test_m4_upgrade_preserves_existing_user_submission_evaluation_and_trace(app):
    with TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as client:
        identity = authenticate_client(client)
        sid = client.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"}).json()["id"]
        receipt = client.post(f"/api/sessions/{sid}/submissions", json={"content": FIXTURE_SUBMISSION_CONTENT}).json()
    with app.state.session_factory() as db:
        checkpoint = db.get(SolveSession, sid).trace_head_sha256
        evaluation = db.get(Evaluation, receipt["evaluation_id"]).result
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    command.downgrade(config, "0007_operations")
    command.upgrade(config, "head")
    with app.state.session_factory() as db:
        assert db.get(User, identity["user"]["id"]).is_active
        assert db.get(Submission, receipt["submission_id"]).content == FIXTURE_SUBMISSION_CONTENT
        assert db.get(Evaluation, receipt["evaluation_id"]).result == evaluation
        assert db.get(SolveSession, sid).trace_head_sha256 == checkpoint
        assert db.scalar(select(func.count()).select_from(JudgeJob)) == 0
