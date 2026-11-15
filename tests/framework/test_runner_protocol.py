"""Offline Runner boundary tests; synthetic transport is not OS isolation."""
import asyncio
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import socket
import subprocess
from uuid import uuid4

import pytest

from praxioj.execution import (ExecutionRequest, ExecutionValidationError, MockJudgeBackend, MockRunnerTransport, RunnerCancellation,
    RunnerCancellationAck, RunnerChannelError, RunnerDispatch, RunnerGrant, RunnerHeartbeat,
    RunnerHeartbeatAck, RunnerIdentity, RunnerResultSubmission, RunnerRuntimeStatus,
    UnavailableExecutionBackend, build_mock_request, canonical_json, parse_runner_message,
    runner_binding, validate_execution_result)


@pytest.fixture
def runner_dispatch():
    request = build_mock_request(request_id=uuid4(), job_id=uuid4(), attempt_id=uuid4(), session_id=uuid4(),
        fence=1, submission_id=uuid4(), trace_head_sha256=None, trace_next_sequence_number=1,
        deadline=datetime.now(UTC) + timedelta(seconds=60), criteria=[{"id": "fixture", "max_score": 100.0}])
    identity = RunnerIdentity(runner_id="fixed-mock-runner")
    grants = tuple(RunnerGrant(grant_id=uuid4(), token=letter * 43, audience=identity.runner_id,
        operation=operation, binding=runner_binding(request), expires_at=request.deadline)
        for operation, letter in (("heartbeat", "A"), ("submit_result", "B"), ("cancel", "C")))
    return RunnerDispatch(protocol_version="1.0", identity=identity, request=request, grants=grants)


def test_runner_round_trip_has_explicit_synthetic_identity_and_strict_result(runner_dispatch):
    dispatch = runner_dispatch
    assert parse_runner_message(RunnerDispatch, canonical_json(dispatch)) == dispatch
    transport = MockRunnerTransport(dispatch.identity.runner_id)
    runtime = parse_runner_message(RunnerRuntimeStatus, transport.availability())
    assert runtime.availability.status == "available" and runtime.identity.host_isolation_verified is False
    transport.open(canonical_json(dispatch))
    result = parse_runner_message(RunnerResultSubmission, asyncio.run(transport.execute()))
    assert validate_execution_result(dispatch.request, result.result).status == "completed"
    assert result.grant.operation == "submit_result"
    for grant in dispatch.grants:
        assert grant.token not in repr(dispatch) and grant.token not in repr(grant) and grant.token not in repr(result)
    with pytest.raises(RunnerChannelError, match="already_sent"):
        asyncio.run(transport.execute())
    transport.close()
    transport.close()
    with pytest.raises(RunnerChannelError, match="closed"):
        transport.heartbeat()


@pytest.mark.parametrize("raw", [b"\xff", b" " * 65_537,
    '{"protocol_version":"1.0","protocol_version":"2.0"}', '{"x":NaN}',
    {"x": [[[[[[[[[[[[[[[[[[0]]]]]]]]]]]]]]]]]]}, {"x": [0] * 10_001}])
def test_runner_messages_preserve_m5_wire_bounds(raw):
    with pytest.raises(ExecutionValidationError):
        parse_runner_message(RunnerDispatch, raw)


@pytest.mark.parametrize("change", ["protocol", "policy", "request_digest", "fence", "expiry", "audience", "operation", "duplicate"])
def test_dispatch_rejects_forged_or_unbound_grants(runner_dispatch, change):
    raw = runner_dispatch.model_dump(mode="json")
    grant = raw["grants"][0]
    if change == "protocol":
        raw["protocol_version"] = "2.0"
    elif change == "policy":
        grant["binding"]["policy_digest"] = "0" * 64
    elif change == "request_digest":
        grant["binding"]["request_digest"] = "0" * 64
    elif change == "fence":
        grant["binding"]["fence"] += 1
    elif change == "expiry":
        grant["expires_at"] = (runner_dispatch.request.deadline + timedelta(seconds=1)).isoformat()
    elif change == "audience":
        grant["audience"] = "another-runner"
    elif change == "operation":
        grant["operation"] = "submit_result"
    else:
        raw["grants"][1]["token"] = grant["token"]
    with pytest.raises(ExecutionValidationError) as rejected:
        parse_runner_message(RunnerDispatch, raw)
    assert all(item.token not in str(rejected.value) for item in runner_dispatch.grants)


def test_model_copy_cannot_bypass_nested_request_validation(runner_dispatch):
    bad_request = runner_dispatch.request.model_copy(update={"policy_digest": "0" * 64})
    forged = runner_dispatch.model_copy(update={"request": bad_request})
    with pytest.raises(ExecutionValidationError):
        parse_runner_message(RunnerDispatch, forged)


def test_heartbeat_ack_correlates_rotated_grant_and_server_times(runner_dispatch):
    transport = MockRunnerTransport(runner_dispatch.identity.runner_id)
    transport.open(canonical_json(runner_dispatch))
    heartbeat = parse_runner_message(RunnerHeartbeat, transport.heartbeat())
    with pytest.raises(RunnerChannelError, match="ack_required"):
        transport.heartbeat()
    old = heartbeat.grant
    grant = RunnerGrant(**{**old.model_dump(), "grant_id": uuid4(), "token": "D" * 43})
    ack = RunnerHeartbeatAck(protocol_version="1.0", message_id=heartbeat.message_id,
        identity=transport.identity, grant=grant, heartbeat_at=runner_dispatch.request.deadline - timedelta(seconds=50),
        lease_expires_at=runner_dispatch.request.deadline - timedelta(seconds=35),
        expires_at=runner_dispatch.request.deadline, deadline_at=runner_dispatch.request.deadline)
    wrong = ack.model_copy(update={"message_id": uuid4()})
    with pytest.raises(RunnerChannelError, match="ack_mismatch"):
        transport.acknowledge(canonical_json(wrong))
    transport.acknowledge(canonical_json(ack))
    with pytest.raises(RunnerChannelError, match="ack_mismatch"):
        transport.acknowledge(canonical_json(ack))
    assert parse_runner_message(RunnerHeartbeat, transport.heartbeat()).grant == grant


def test_wrong_identity_busy_transport_and_unavailable_status(runner_dispatch):
    wrong = MockRunnerTransport("wrong-runner")
    with pytest.raises(RunnerChannelError, match="identity_mismatch"):
        wrong.open(canonical_json(runner_dispatch))
    correct = MockRunnerTransport(runner_dispatch.identity.runner_id)
    correct.open(canonical_json(runner_dispatch))
    with pytest.raises(RunnerChannelError, match="busy"):
        correct.open(canonical_json(runner_dispatch))
    unavailable = MockRunnerTransport(backend=UnavailableExecutionBackend())
    status = parse_runner_message(RunnerRuntimeStatus, unavailable.availability())
    assert status.availability.status == "unavailable"


def test_cancellation_bound_to_grant_and_mock_cleanup_only(runner_dispatch):
    transport = MockRunnerTransport(runner_dispatch.identity.runner_id)
    transport.open(canonical_json(runner_dispatch))
    cancellation = transport.cancellation_poll()
    wrong = json.loads(cancellation)
    wrong["grant"]["token"] = "X" * 43
    with pytest.raises(RunnerChannelError, match="cancellation_invalid"):
        transport.cancel(canonical_json(wrong))
    ack = parse_runner_message(RunnerCancellationAck, transport.cancel(cancellation))
    assert ack.cleanup.status == "not_required" and ack.cleanup.reason == "synthetic_no_resources"
    with pytest.raises(RunnerChannelError, match="cancellation_invalid"):
        transport.cancel(cancellation)
    result = parse_runner_message(RunnerResultSubmission, asyncio.run(transport.execute()))
    assert result.result["status"] == "cancelled"
    forged = ack.model_dump(mode="json")
    forged["cleanup"] = {"status": "completed", "reason": "runtime_reported"}
    with pytest.raises(ExecutionValidationError):
        parse_runner_message(RunnerCancellationAck, forged)


def test_fixed_transport_does_not_open_process_network_or_host_file(runner_dispatch, monkeypatch):
    transport = MockRunnerTransport(runner_dispatch.identity.runner_id)
    transport.open(canonical_json(runner_dispatch))
    loop = asyncio.new_event_loop()

    def forbidden(*args, **kwargs):
        raise AssertionError("synthetic Runner must not execute host operations")

    with monkeypatch.context() as guard:
        guard.setattr(subprocess, "Popen", forbidden)
        guard.setattr(socket, "socket", forbidden)
        guard.setattr(Path, "read_bytes", forbidden)
        guard.setattr(Path, "write_bytes", forbidden)
        result = loop.run_until_complete(transport.execute())
        assert parse_runner_message(RunnerResultSubmission, result).result["provenance"] == "synthetic_mock"
    loop.close()


def test_backend_receives_only_request_and_transport_is_single_flight(runner_dispatch):
    received = []

    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()

        class DelayedMock(MockJudgeBackend):
            async def execute(self, request):
                received.append(request)
                entered.set()
                await release.wait()
                return await super().execute(request)

        transport = MockRunnerTransport(runner_dispatch.identity.runner_id, backend=DelayedMock())
        wire = canonical_json(runner_dispatch)
        transport.open(wire)
        pending = asyncio.create_task(transport.execute())
        await entered.wait()
        with pytest.raises(RunnerChannelError, match="already_sent"):
            await transport.execute()
        transport.close()
        with pytest.raises(RunnerChannelError, match="busy"):
            transport.open(wire)
        release.set()
        with pytest.raises(RunnerChannelError, match="closed"):
            await pending
        transport.open(wire)
        transport.close()

    asyncio.run(exercise())
    assert len(received) == 1 and isinstance(received[0], ExecutionRequest)
    assert set(type(received[0]).model_fields) == set(type(runner_dispatch.request).model_fields)
    for grant in runner_dispatch.grants:
        assert grant.token not in canonical_json(received[0]).decode()
