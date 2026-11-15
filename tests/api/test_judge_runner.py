"""Trusted Mock-channel integration; no remote host or isolation is claimed."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from praxioj.execution import (ExecutionValidationError, FIXTURE_SUBMISSION_CONTENT, MockRunnerTransport, RunnerChannelError,
    RunnerHeartbeatAck, RunnerIdentity, RunnerResultSubmission, UnavailableExecutionBackend,
    canonical_json, parse_runner_message)
from praxioj_api.judge import JudgeError
from praxioj_api.judge_models import JudgeAttempt, JudgeJob
from praxioj_api.judge_runner import JudgeRunnerGateway
from praxioj_api.models import User, utcnow
from test_judge_broker import enqueue, setup_judge
from conftest import authenticate_client


def open_channel(broker, lease, transport=None):
    transport = transport or MockRunnerTransport(lease.worker_id)
    gateway = JudgeRunnerGateway(broker, lease, transport.identity)
    wire = gateway.start(transport.availability(), observed_identity=transport.identity)
    transport.open(wire)
    return gateway, transport, wire


@pytest.fixture
def runner_channel(app, setup_judge):
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    lease = broker.claim("fixed-mock-runner", job.id)
    gateway, transport, wire = open_channel(broker, lease)
    return broker, lease, gateway, transport, wire


def test_round_trip_heartbeat_result_and_private_capability_boundary(app, runner_channel):
    broker, lease, gateway, transport, dispatch = runner_channel
    raw_dispatch = json.loads(dispatch)
    tokens = [item["token"] for item in raw_dispatch["grants"]]
    assert gateway.active_grants == 3 and lease.token not in dispatch.decode()
    assert lease.token not in repr(gateway)
    for token in tokens:
        assert token not in repr(gateway._grants)
    assert set(raw_dispatch) == {"protocol_version", "identity", "request", "grants"}
    heartbeat = transport.heartbeat()
    ack = gateway.heartbeat(heartbeat, observed_identity=transport.identity)
    renewal = parse_runner_message(RunnerHeartbeatAck, ack)
    assert renewal.heartbeat_at < renewal.lease_expires_at <= renewal.expires_at <= renewal.deadline_at
    transport.acknowledge(ack)
    assert gateway.active_grants == 3
    with pytest.raises(RunnerChannelError, match="grant_invalid"):
        gateway.heartbeat(heartbeat, observed_identity=transport.identity)
    result = asyncio.run(transport.execute())
    public = gateway.submit_result(result, observed_identity=transport.identity)
    assert public["state"] == "COMPLETED" and public["assessment"]["independent_execution_evidence"] is False
    assert gateway.active_grants == 0 and gateway._lease is None
    with pytest.raises(RunnerChannelError, match="closed"):
        gateway.submit_result(result, observed_identity=transport.identity)
    with app.state.session_factory() as db:
        assert not db.get(JudgeJob, lease.job_id).reservation_active


@pytest.mark.parametrize("field", ["token", "expires_at", "policy_digest", "request_digest", "fence", "operation", "audience"])
def test_grant_metadata_cannot_be_changed_or_cross_used(app, runner_channel, field):
    _, lease, gateway, transport, _ = runner_channel
    heartbeat = transport.heartbeat()
    raw = json.loads(heartbeat)
    grant = raw["grant"]
    if field == "token":
        grant["token"] = "X" * 43
    elif field == "expires_at":
        grant["expires_at"] = (lease.request.deadline + timedelta(seconds=10)).isoformat()
    elif field in {"policy_digest", "request_digest"}:
        grant["binding"][field] = "0" * 64
    elif field == "fence":
        grant["binding"][field] += 1
    elif field == "operation":
        grant["operation"] = "submit_result"
    else:
        grant["audience"] = "another-runner"
    with pytest.raises((RunnerChannelError, ExecutionValidationError)):
        gateway.heartbeat(canonical_json(raw), observed_identity=transport.identity)
    # Invalid authority cannot revoke or consume the genuine heartbeat grant.
    transport.acknowledge(gateway.heartbeat(heartbeat, observed_identity=transport.identity))
    assert gateway.submit_result(asyncio.run(transport.execute()), observed_identity=transport.identity)["state"] == "COMPLETED"


def test_observed_and_payload_identity_are_independent_bindings(runner_channel):
    _, lease, gateway, transport, _ = runner_channel
    heartbeat = transport.heartbeat()
    with pytest.raises(RunnerChannelError, match="identity_mismatch"):
        gateway.heartbeat(heartbeat, observed_identity=RunnerIdentity(runner_id="untrusted-assertion"))
    raw = json.loads(heartbeat)
    raw["identity"]["runner_id"] = "untrusted-assertion"
    raw["grant"]["audience"] = "untrusted-assertion"
    with pytest.raises(RunnerChannelError, match="grant_invalid"):
        gateway.heartbeat(canonical_json(raw), observed_identity=transport.identity)
    transport.acknowledge(gateway.heartbeat(heartbeat, observed_identity=transport.identity))
    with pytest.raises(RunnerChannelError, match="worker_mismatch"):
        JudgeRunnerGateway(gateway._broker, lease, RunnerIdentity(runner_id="another-worker"))


@pytest.mark.parametrize("mutation", ["capability_expiry", "lease_expiry", "policy", "fence"])
def test_db_authority_overrules_unchanged_client_grant(app, runner_channel, mutation):
    _, lease, gateway, transport, _ = runner_channel
    with app.state.session_factory.begin() as db:
        attempt, job = db.get(JudgeAttempt, lease.attempt_id), db.get(JudgeJob, lease.job_id)
        if mutation == "capability_expiry":
            attempt.expires_at = utcnow() - timedelta(seconds=1)
        elif mutation == "lease_expiry":
            attempt.lease_expires_at = utcnow() - timedelta(seconds=1)
        elif mutation == "fence":
            job.fence += 1
        else:
            job.spec = {**job.spec, "untrusted_policy_override": True}
    with pytest.raises(RunnerChannelError, match="authority_lost"):
        gateway.heartbeat(transport.heartbeat(), observed_identity=transport.identity)
    assert gateway.active_grants == 0


def test_expired_result_is_rejected_and_channel_dropped(app, runner_channel):
    _, lease, gateway, transport, _ = runner_channel
    result = asyncio.run(transport.execute())
    with app.state.session_factory.begin() as db:
        db.get(JudgeAttempt, lease.attempt_id).expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(JudgeError, match="execution_authority_expired"):
        gateway.submit_result(result, observed_identity=transport.identity)
    assert gateway.active_grants == 0
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, lease.job_id).assessment is None


def test_runner_cannot_cancel_db_job_and_only_confirms_persisted_owner_cancellation(app, setup_judge, runner_channel):
    broker, lease, gateway, transport, _ = runner_channel
    poll = transport.cancellation_poll()
    with pytest.raises(RunnerChannelError, match="job_not_cancelled"):
        gateway.cancellation(poll, observed_identity=transport.identity)
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, lease.job_id).state == "RUNNING"
    with app.state.session_factory.begin() as db:
        broker.cancel(db, db.get(User, setup_judge[1]), lease.job_id)
    signal = gateway.cancellation(poll, observed_identity=transport.identity)
    ack = transport.cancel(signal)
    cleanup = gateway.acknowledge_cleanup(ack, observed_identity=transport.identity)
    assert cleanup.status == "not_required" and cleanup.reason == "synthetic_no_resources"
    assert gateway.active_grants == 0
    with pytest.raises(RunnerChannelError, match="cleanup_invalid"):
        gateway.acknowledge_cleanup(ack, observed_identity=transport.identity)
    with pytest.raises(RunnerChannelError, match="closed"):
        gateway.heartbeat(poll, observed_identity=transport.identity)


def test_channel_loss_discards_grants_and_durable_lease_recovers(app, runner_channel):
    broker, lease, gateway, transport, _ = runner_channel
    result = asyncio.run(transport.execute())
    gateway.close()
    gateway.close()
    assert gateway.active_grants == 0 and gateway._lease is None
    with pytest.raises(RunnerChannelError, match="closed"):
        gateway.submit_result(result, observed_identity=transport.identity)
    assert broker.claim("replacement", lease.job_id) is None
    with app.state.session_factory.begin() as db:
        db.get(JudgeAttempt, lease.attempt_id).lease_expires_at = utcnow() - timedelta(seconds=1)
    assert broker.recover() == 1
    assert broker.recover() == 0
    with app.state.session_factory() as db:
        job = db.get(JudgeJob, lease.job_id)
        assert job.state == "FAILED" and not job.reservation_active and job.assessment is None


def test_unavailable_transport_never_silently_falls_back_to_mock(app, setup_judge):
    broker = setup_judge[0]
    job = enqueue(app, setup_judge)
    lease = broker.claim("unavailable-runner", job.id)
    transport = MockRunnerTransport(lease.worker_id, backend=UnavailableExecutionBackend())
    gateway = JudgeRunnerGateway(broker, lease, transport.identity)
    with pytest.raises(RunnerChannelError, match="runtime_unavailable"):
        gateway.start(transport.availability(), observed_identity=transport.identity)
    assert gateway.active_grants == 0
    with app.state.session_factory() as db:
        assert db.get(JudgeJob, job.id).error_code == "backend_unavailable"


def test_invalid_runner_result_uses_existing_broker_validator(app, runner_channel):
    _, lease, gateway, transport, _ = runner_channel
    result = json.loads(asyncio.run(transport.execute()))
    result["result"]["policy_digest"] = "0" * 64
    public = gateway.submit_result(canonical_json(result), observed_identity=transport.identity)
    assert public["state"] == "FAILED" and public["error_code"] == "invalid_result"
    assert public["assessment"] is None and public["result"] is None and gateway.active_grants == 0


def test_cross_account_channel_grants_cannot_be_swapped(app, setup_judge, runner_channel):
    broker, _, gateway, transport, _ = runner_channel
    with TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as other:
        identity = authenticate_client(other)
        sid = other.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"}).json()["id"]
        sub = other.post(f"/api/sessions/{sid}/submissions", json={"content": FIXTURE_SUBMISSION_CONTENT}).json()["submission_id"]
        with app.state.session_factory.begin() as db:
            db.get(User, identity["user"]["id"]).role = "administrator"
    second = enqueue(app, (broker, identity["user"]["id"], sid, sub))
    lease = broker.claim(transport.identity.runner_id, second.id)
    other_gateway, other_transport, _ = open_channel(broker, lease)
    foreign_result = asyncio.run(transport.execute())
    with pytest.raises(RunnerChannelError, match="grant_invalid"):
        other_gateway.submit_result(foreign_result, observed_identity=other_transport.identity)
    assert other_gateway.submit_result(asyncio.run(other_transport.execute()), observed_identity=other_transport.identity)["state"] == "COMPLETED"
    assert gateway.submit_result(foreign_result, observed_identity=transport.identity)["state"] == "COMPLETED"


def test_gateway_failure_discards_grants_and_uses_controlled_broker_code(app, runner_channel):
    _, lease, gateway, _, _ = runner_channel
    assert gateway.fail("private exception detail")
    assert not gateway.fail()
    assert gateway.active_grants == 0 and gateway._lease is None
    with app.state.session_factory() as db:
        job = db.get(JudgeJob, lease.job_id)
        assert job.state == "FAILED" and job.error_code == "backend_error" and not job.reservation_active


def test_heartbeat_grant_race_has_one_rotation_and_one_db_renewal(runner_channel, monkeypatch):
    broker, _, gateway, transport, _ = runner_channel
    heartbeat = transport.heartbeat()
    barrier = Barrier(2)
    calls = []
    original = broker.renew

    def renew(lease):
        calls.append(1)
        return original(lease)

    monkeypatch.setattr(broker, "renew", renew)

    def race(_):
        barrier.wait()
        try:
            return gateway.heartbeat(heartbeat, observed_identity=transport.identity)
        except RunnerChannelError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, range(2)))
    assert sum(item is not None for item in results) == 1 and len(calls) == 1
    assert gateway.active_grants == 3


@pytest.mark.postgres
def test_independent_channel_result_race_still_has_one_db_commit(app, runner_channel):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for independent-channel result race")
    broker, lease, gateway, transport, _ = runner_channel
    other_gateway, other_transport, _ = open_channel(broker, lease)
    channels = [(gateway, transport), (other_gateway, other_transport)]
    messages = [asyncio.run(channel.execute()) for _, channel in channels]
    barrier = Barrier(2)

    def race(index):
        control, channel = channels[index]
        barrier.wait()
        try:
            return control.submit_result(messages[index], observed_identity=channel.identity)["state"]
        except JudgeError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(race, range(2))) == ["COMPLETED", "rejected"]
    assert gateway.active_grants == other_gateway.active_grants == 0
