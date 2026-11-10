"""M4 admission, accounting, observability and worker maintenance invariants."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from conftest import authenticate_client
from praxioj.runtime import AIRuntime, MockProvider
from praxioj_api.job_models import Job
from praxioj_api.jobs import JobRepository
from praxioj_api.main import create_app
from praxioj_api.maintenance import run_maintenance
from praxioj_api.models import AuthRateLimit, ProviderCall, SolveSession, User, WorkspaceRun, utcnow
from praxioj_api.quota_models import ProviderReservation, QuotaBucket, TraceUsage, WorkerRecord
from praxioj_api.quotas import (TERMINAL_BYTE_RESERVE, TERMINAL_EVENT_RESERVE, cleanup_quota_records,
    reserve_provider, settle_provider)
from praxioj_api.registry import register_directory
from praxioj_api.worker import Worker

ROOT = Path(__file__).resolve().parents[2]


def configured(app, **changes):
    return create_app(replace(app.state.settings, **changes))


def client_for(app):
    return TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"})


def session_for(client, problem="release-plan"):
    response = client.post("/api/sessions", json={"problem_id": problem, "version": "1.0.0"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def run_for(client, sid, content="hello"):
    return client.post(f"/api/sessions/{sid}/runs", json={"content": content, "request_id": str(uuid4())})


def test_session_and_storage_admission_preserves_existing_data(app):
    application = configured(app, account_active_sessions=1, account_retained_sessions=2)
    with client_for(application) as client:
        authenticate_client(client)
        sid = session_for(client)
        blocked = client.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"})
        assert blocked.status_code == 429 and blocked.headers["retry-after"] == "60"
        assert client.post(f"/api/sessions/{sid}/end", json={}).status_code == 200
        next_sid = session_for(client)
        client.post(f"/api/sessions/{next_sid}/end", json={})
        assert client.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"}).status_code == 429
        usage = client.get("/api/account/usage").json()
        assert usage["retained_sessions"] == 2 and usage["active_sessions"] == 0
        assert client.get(f"/api/sessions/{sid}").status_code == 200


def test_storage_capacity_is_reserved_before_session_and_initial_files(app):
    application = configured(app, account_artifact_capacity_bytes=1)
    with client_for(application) as client:
        authenticate_client(client)
        response = client.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"})
        assert response.status_code == 429 and response.json()["detail"] == "account_artifact_capacity"
        assert client.get("/api/account/usage").json()["retained_sessions"] == 0


def test_pending_cancellation_releases_concurrency_without_refunding_attempts(app):
    application = configured(app, account_active_runs=1)
    with client_for(application) as client:
        authenticate_client(client)
        one, two = session_for(client), session_for(client)
        rid = run_for(client, one).json()["id"]
        assert run_for(client, two).status_code == 429
        assert client.post(f"/api/runs/{rid}/cancel", json={}).status_code == 200
        assert run_for(client, two).status_code == 202
        usage = client.get("/api/account/usage").json()
        assert usage["active_runs"] == 1 and usage["daily"]["model_calls"] == 0
        assert usage["daily"]["reserved_policy_units"] == 0


def test_daily_model_limit_blocks_followup_and_keeps_mock_usage_estimated(app):
    application = configured(app, account_daily_model_calls=1)
    with application.state.session_factory.begin() as db:
        register_directory(db, ROOT / "examples/problems/workspace-plan")
    with client_for(application) as client:
        authenticate_client(client)
        sid = session_for(client, "workspace-plan")
        rid = run_for(client, sid, "save a release plan").json()["id"]
        assert asyncio.run(Worker(application).run_once())
        run = client.get(f"/api/runs/{rid}").json()
        assert run["status"] == "failed" and run["error"]["code"] == "user_model_call_limit"
        daily = client.get("/api/account/usage").json()["daily"]
        assert daily["model_calls"] == 1 and daily["tool_calls"] == 1
        assert daily["uncertain_calls"] == 1 and daily["reserved_policy_units"] >= 16384
        assert daily["input_tokens"] == daily["output_tokens"] == 0
        assert client.get(f"/api/sessions/{sid}/usage").json()["estimated"] is True


def test_token_reservation_prevents_dispatch_without_inventing_usage(app):
    application = configured(app, account_daily_token_allowance=1)
    with client_for(application) as client:
        authenticate_client(client)
        sid = session_for(client)
        rid = run_for(client, sid).json()["id"]
        assert asyncio.run(Worker(application).run_once())
        assert client.get(f"/api/runs/{rid}").json()["error"]["code"] == "user_token_allowance"
        assert client.get("/api/account/usage").json()["daily"]["model_calls"] == 0
        assert client.get(f"/api/sessions/{sid}/usage").json()["model_calls"] == 0


def test_trace_soft_limit_preserves_terminal_recovery_and_submission(app):
    application = configured(app, session_trace_max_events=3)
    with client_for(application) as client:
        authenticate_client(client)
        sid = session_for(client)
        rid = run_for(client, sid).json()["id"]
        assert asyncio.run(Worker(application).run_once()) is False  # failed before claim/provider
        assert client.get(f"/api/runs/{rid}").json()["error"]["code"] == "trace_storage_limit"
        assert run_for(client, sid).status_code == 429
        submitted = client.post(f"/api/sessions/{sid}/submissions", json={"content": "Goal Verification Risk"})
        assert submitted.status_code == 201, submitted.text
        trace = client.get(f"/api/sessions/{sid}/trace").json()
        assert len(trace) <= 3 + TERMINAL_EVENT_RESERVE
        assert client.get(f"/api/sessions/{sid}/trace/integrity").json()["status"] == "verified"


def test_admin_operations_does_not_expose_other_users_to_participant(app):
    with client_for(app) as client:
        auth = authenticate_client(client)
        sid = session_for(client)
        rid = run_for(client, sid).json()["id"]
        worker = Worker(app)
        assert asyncio.run(worker.run_once())
        assert client.get("/api/admin/operations").status_code == 403
        with app.state.session_factory.begin() as db:
            db.get(User, auth["user"]["id"]).role = "administrator"
        result = client.get("/api/admin/operations")
        assert result.status_code == 200
        data = result.json()
        assert data["queue"]["completed"] == 1
        assert data["processing"]["completed"] == 1 and data["processing"]["mean_run_seconds"] >= 0
        assert data["api_process"]["requests"] > 0
        assert data["workers"][0]["id"] == worker.worker_id
        assert "claim_token" not in result.text and "password" not in result.text
        public = client.get(f"/api/runs/{rid}").text
        assert worker.worker_id not in public


def test_worker_graceful_shutdown_drains_then_stops_claiming(app):
    application = configured(app, worker_shutdown_seconds=1)
    entered = asyncio.Event()
    class SlowRuntime:
        async def respond(self, *args):
            entered.set()
            await asyncio.sleep(.1)
            return await AIRuntime(MockProvider()).respond(*args)
    application.state.runtime = SlowRuntime()
    with client_for(application) as client:
        authenticate_client(client)
        sid = session_for(client)
        rid = run_for(client, sid).json()["id"]
        worker = Worker(application)
        async def scenario():
            task = asyncio.create_task(worker.run_once())
            await asyncio.wait_for(entered.wait(), 5)
            worker.stop.set()
            assert await task
            assert not await worker.run_once()
        asyncio.run(scenario())
        assert client.get(f"/api/runs/{rid}").json()["status"] == "completed"
        with application.state.session_factory() as db:
            assert db.get(WorkerRecord, worker.worker_id).state == "STOPPED"


def test_worker_forced_shutdown_keeps_uncertain_reservation(app):
    application = configured(app, worker_shutdown_seconds=.01)
    entered = asyncio.Event()
    class StalledRuntime:
        async def respond(self, *args):
            entered.set()
            await asyncio.Event().wait()
    application.state.runtime = StalledRuntime()
    with client_for(application) as client:
        authenticate_client(client)
        sid = session_for(client)
        rid = run_for(client, sid).json()["id"]
        worker = Worker(application)
        async def scenario():
            task = asyncio.create_task(worker.run_once())
            await asyncio.wait_for(entered.wait(), 5)
            worker.stop.set()
            assert await asyncio.wait_for(task, 5)
        asyncio.run(scenario())
        run = client.get(f"/api/runs/{rid}").json()
        assert run["error"]["code"] == "worker_stopped" and run["job"]["external_effect_uncertain"]
        daily = client.get("/api/account/usage").json()["daily"]
        assert daily["model_calls"] == 1 and daily["uncertain_calls"] == 1 and daily["reserved_policy_units"] > 0
        assert daily["input_tokens"] == daily["output_tokens"] == 0


def test_standalone_maintenance_recovers_without_workers_and_is_repeatable(app):
    with client_for(app) as client:
        authenticate_client(client)
        sid = session_for(client)
        rid = run_for(client, sid).json()["id"]
        assert JobRepository(app.state.session_factory).claim("synthetic-stopped-worker")
        with app.state.session_factory.begin() as db:
            db.get(Job, rid).lease_expires_at = utcnow() - timedelta(seconds=1)
            db.add(AuthRateLimit(key_hash="a" * 64, window_start=utcnow() - timedelta(days=2), count=10))
        result = run_maintenance(app.state.session_factory, app.state.settings)
        assert result["recovered_jobs"] == 1 and result["auth_rate_limits"] == 1
        assert run_maintenance(app.state.session_factory, app.state.settings)["recovered_jobs"] == 0
        assert client.get(f"/api/runs/{rid}").json()["error"]["code"] == "lease_expired"


def test_old_reserved_window_is_not_deleted_or_recreated_with_negative_usage(app):
    with client_for(app) as client:
        authenticate_client(client)
        sid = session_for(client)
        with app.state.session_factory.begin() as db:
            session = db.get(SolveSession, sid)
            call = ProviderCall(session_id=sid)
            db.add(call); db.flush()
            reserve_provider(db, session, call, app.state.settings, input_bytes=100, output_limit=10)
            call_id = call.id
            future = utcnow() + timedelta(days=3)
            assert cleanup_quota_records(db, future)["quota_buckets"] == 0
            call.input_tokens, call.output_tokens = 10, 20
            call.status = "completed"
            settle_provider(db, call)
            rows = list(db.scalars(select(QuotaBucket)))
            assert all(r.reserved_units == 0 and r.input_tokens == 10 and r.output_tokens == 20 for r in rows)
        with app.state.session_factory.begin() as db:
            counts = cleanup_quota_records(db, future)
            assert counts["reservations"] == 1 and counts["quota_buckets"] == 3


@pytest.mark.postgres
def test_concurrent_account_run_admission_is_atomic(app):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for concurrent quota reservations")
    application = configured(app, account_active_runs=1)
    with client_for(application) as first, client_for(application) as second:
        authenticate_client(first)
        second.cookies.update(first.cookies)
        second.headers["X-CSRF-Token"] = first.headers["X-CSRF-Token"]
        one, two = session_for(first), session_for(first)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda pair: run_for(*pair).status_code, [(first, one), (second, two)]))
        assert sorted(outcomes) == [202, 429]
        assert first.get("/api/account/usage").json()["active_runs"] == 1


@pytest.mark.postgres
def test_system_backpressure_and_capacity_across_accounts(app):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for concurrent system admission")
    application = configured(app, queue_max_pending=1, worker_max_running=1)
    with client_for(application) as first, client_for(application) as second:
        authenticate_client(first); authenticate_client(second)
        one, two = session_for(first), session_for(second)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda pair: run_for(*pair), [(first, one), (second, two)]))
        assert sorted(r.status_code for r in responses) == [202, 429]
        repository = JobRepository(application.state.session_factory, max_running=1)
        lease = repository.claim("first-worker")
        assert lease is not None
        loser = (first, one) if responses[0].status_code == 429 else (second, two)
        assert run_for(*loser).status_code == 202
        assert repository.claim("second-worker") is None
        owner = first if responses[0].status_code == 202 else second
        assert owner.post(f"/api/runs/{lease.run_id}/cancel", json={}).status_code == 200
        assert repository.claim("second-worker") is not None


def test_terminal_headroom_handles_maximum_pending_tool_batch_without_truncation(app):
    from praxioj.tracing import EventType
    from praxioj_api.models import ConversationMessage
    from praxioj_api.runs import RunManager
    from praxioj_api.services import append_trace
    with client_for(app) as client:
        authenticate_client(client)
        sid = session_for(client)
        rid = run_for(client, sid).json()["id"]
        lease = JobRepository(app.state.session_factory).claim("headroom-test")
        tools = [{"id": f"pending-{i}", "name": "write_file", "arguments": {"path": f"f{i}.txt", "content": "x" * 30000}}
                 for i in range(32)]
        with app.state.session_factory.begin() as db:
            session = db.get(SolveSession, sid)
            db.add(ConversationMessage(session_id=sid, position=2, role="assistant", content="", tool_calls=tools))
            append_trace(db, session, EventType.ASSISTANT_MESSAGE, {"content": "", "tool_calls": tools})
            usage = db.get(TraceUsage, sid)
            session.profile_snapshot = {**session.profile_snapshot, "resource_policy": {
                **session.profile_snapshot["resource_policy"], "trace_max_bytes": usage.bytes_used,
                "trace_max_events": session.next_sequence_number - 1}}
            regular_bytes, regular_events = usage.bytes_used, session.next_sequence_number - 1
        assert RunManager(app, lease).finish(rid, "failed", "worker_stopped")
        response = client.post(f"/api/sessions/{sid}/submissions", json={"content": "Goal Verification Risk"})
        assert response.status_code == 201, response.text
        events = client.get(f"/api/sessions/{sid}/trace").json()
        requested = [e for e in events if e["event_type"] == "TOOL_CALL_REQUESTED"]
        assert len(requested) == 32
        assert all(len(e["payload"]["arguments"]["content"]) == 30000 for e in requested)
        with app.state.session_factory() as db:
            assert db.get(TraceUsage, sid).bytes_used <= regular_bytes + TERMINAL_BYTE_RESERVE
        assert len(events) <= regular_events + TERMINAL_EVENT_RESERVE
        assert client.get(f"/api/sessions/{sid}/trace/integrity").json()["status"] == "verified"


def test_maintenance_closes_expired_pending_jobs_without_a_worker(app):
    with client_for(app) as client:
        authenticate_client(client)
        sid = session_for(client)
        rid = run_for(client, sid).json()["id"]
        with app.state.session_factory.begin() as db:
            db.get(SolveSession, sid).trace_expires_at = utcnow() - timedelta(seconds=1)
        result = run_maintenance(app.state.session_factory, app.state.settings)
        assert result["recovered_jobs"] == result["purged_trace_sessions"] == 1
        assert client.get(f"/api/runs/{rid}").json()["error"]["code"] == "session_expired"
        assert client.get(f"/api/sessions/{sid}/trace").status_code == 410
        with app.state.session_factory() as db:
            assert db.scalar(select(func.count()).select_from(ProviderCall)) == 0


def test_author_problem_quota_is_scoped_to_owned_problem(app):
    with client_for(app) as client, client_for(app) as foreign:
        owner = authenticate_client(client)
        authenticate_client(foreign)
        with app.state.session_factory.begin() as db:
            from praxioj_api.models import Problem
            db.get(User, owner["user"]["id"]).role = "author"
            db.get(Problem, "release-plan").author_id = owner["user"]["id"]
        sid = session_for(foreign)
        run_for(foreign, sid)
        assert asyncio.run(Worker(app).run_once())
        result = client.get("/api/author/problems/release-plan/usage")
        assert result.status_code == 200 and result.json()["daily"]["model_calls"] == 1
        assert "user_id" not in result.text and sid not in result.text
        assert foreign.get("/api/author/problems/release-plan/usage").status_code == 403
        assert client.get("/api/author/problems/unowned/usage").status_code == 404


@pytest.mark.postgres
def test_two_workers_cannot_overspend_same_account_daily_call_budget(app):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for concurrent provider quota reservation")
    application = configured(app, account_daily_model_calls=1)
    with client_for(application) as client:
        authenticate_client(client)
        one, two = session_for(client), session_for(client)
        ids = [run_for(client, sid).json()["id"] for sid in (one, two)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert all(pool.map(lambda _: asyncio.run(Worker(application).run_once()), range(2)))
        statuses = [client.get(f"/api/runs/{rid}").json()["status"] for rid in ids]
        assert sorted(statuses) == ["completed", "failed"]
        assert client.get("/api/account/usage").json()["daily"]["model_calls"] == 1
        with application.state.session_factory() as db:
            assert db.scalar(select(func.count()).select_from(ProviderCall)) == 1


def test_legacy_over_capacity_trace_can_close_without_rebasing_history(app):
    from sqlalchemy import delete
    with client_for(app) as client:
        authenticate_client(client)
        sid = session_for(client)
        with app.state.session_factory.begin() as db:
            session = db.get(SolveSession, sid)
            # Represents an older, already populated session first seen under a
            # smaller operator cap. Its original event/hash remains unchanged.
            session.profile_snapshot = {**session.profile_snapshot, "resource_policy": {
                **session.profile_snapshot["resource_policy"], "trace_max_bytes": 1}}
            db.execute(delete(TraceUsage).where(TraceUsage.session_id == sid))
        before = client.get(f"/api/sessions/{sid}/trace").json()
        assert run_for(client, sid).status_code == 429
        assert client.post(f"/api/sessions/{sid}/submissions", json={"content": "Goal Verification Risk"}).status_code == 201
        after = client.get(f"/api/sessions/{sid}/trace").json()
        assert after[0] == before[0]
        with app.state.session_factory() as db:
            usage = db.get(TraceUsage, sid)
            baseline = usage.terminal_base_bytes
            assert baseline > 1 and usage.bytes_used <= baseline + TERMINAL_BYTE_RESERVE
        assert client.post(f"/api/sessions/{sid}/end", json={}).status_code == 409
        with app.state.session_factory() as db:
            assert db.get(TraceUsage, sid).terminal_base_bytes == baseline
        assert client.get(f"/api/sessions/{sid}/trace/integrity").json()["status"] == "verified"


def test_fifo_claims_oldest_eligible_pending_job(app):
    with client_for(app) as client:
        authenticate_client(client)
        first_sid, second_sid = session_for(client), session_for(client)
        first = run_for(client, first_sid).json()["id"]
        second = run_for(client, second_sid).json()["id"]
        repository = JobRepository(app.state.session_factory)
        assert repository.claim("fifo-one").run_id == first
        assert repository.claim("fifo-two").run_id == second


def test_heartbeat_database_fault_has_safe_logs_and_no_implicit_retry(app, monkeypatch, caplog):
    from sqlalchemy.exc import OperationalError
    application = configured(app, worker_lease_seconds=1, worker_heartbeat_seconds=.1)
    attempts = []
    class DelayedRuntime:
        async def respond(self, *args):
            attempts.append(1)
            await asyncio.sleep(5)
    application.state.runtime = DelayedRuntime()
    with client_for(application) as client:
        authenticate_client(client)
        sid = session_for(client)
        rid = run_for(client, sid).json()["id"]
        worker = Worker(application)
        def unavailable(*args):
            raise OperationalError("synthetic-private-sql", {"password": "synthetic-private-value"}, RuntimeError("connection refused"))
        monkeypatch.setattr(worker.repository, "heartbeat", unavailable)
        assert asyncio.run(worker.run_once())
        assert len(attempts) == 1
        assert "heartbeat_unavailable" in caplog.text
        assert "synthetic-private" not in caplog.text
        run = client.get(f"/api/runs/{rid}").json()
        assert run["status"] == "failed" and run["job"]["external_effect_uncertain"]
        assert client.get("/api/account/usage").json()["daily"]["uncertain_calls"] == 1


def test_claim_event_overflow_terminalizes_instead_of_stranding_pending_job(app):
    with client_for(app) as client:
        authenticate_client(client)
        sid = session_for(client)
        rid = run_for(client, sid).json()["id"]
        with app.state.session_factory.begin() as db:
            session = db.get(SolveSession, sid)
            session.profile_snapshot = {**session.profile_snapshot, "resource_policy": {
                **session.profile_snapshot["resource_policy"], "trace_max_bytes": db.get(TraceUsage, sid).bytes_used + 1}}
        assert asyncio.run(Worker(app).run_once()) is False
        failed = client.get(f"/api/runs/{rid}").json()
        assert failed["status"] == "failed" and failed["error"]["code"] == "trace_storage_limit"
        assert client.get(f"/api/sessions/{sid}").json()["active_run_id"] is None
        assert client.get(f"/api/sessions/{sid}/trace/integrity").json()["status"] == "verified"


def test_request_telemetry_uses_fixed_categories_and_omits_private_inputs(app, caplog):
    with client_for(app) as client:
        authenticate_client(client)
        response = client.get("/api/sessions/synthetic-private-session-id?secret=synthetic-private-query")
        assert response.status_code == 404
    events = [json.loads(record.message) for record in caplog.records
              if record.name == "praxioj.internal.operations" and record.message.startswith('{"event":"api_request"')]
    assert events and events[-1]["category"] == "sessions"
    assert events[-1]["duration_ms"] >= 0 and events[-1]["status"] == 404
    assert "synthetic-private" not in json.dumps(events)
    assert set(events[-1]) == {"event", "category", "method", "status", "duration_ms"}
