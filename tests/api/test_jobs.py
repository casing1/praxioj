"""Durable queue and fenced worker tests, including separate PostgreSQL processes."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4

from fastapi.testclient import TestClient
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import func, select

from conftest import authenticate_client
from praxioj.runtime import AIRuntime, MockProvider
from praxioj_api.job_models import Job, job_public
from praxioj_api.jobs import JobRepository, LeaseLost, aware, require_lease
from praxioj_api.main import create_app
from praxioj_api.models import ConversationMessage, ProviderCall, SolveSession, TraceEvent, WorkspaceRun, utcnow
from praxioj_api.registry import register_directory
from praxioj_api.runs import RunManager
from praxioj_api.settings import Settings
from praxioj_api.worker import Worker

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def queue_client(app):
    # Deliberately no background worker: API-only execution must stay pending.
    with TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as client:
        authenticate_client(client)
        yield client


def enqueue_run(client, *, problem="release-plan", content="hello", request_id=None, session_id=None, profile=None):
    if session_id is None:
        body = {"problem_id": problem, "version": "1.0.0"}
        if profile:
            body["runtime_profile"] = profile
        response = client.post("/api/sessions", json=body)
        assert response.status_code == 201, response.text
        session_id = response.json()["id"]
    response = client.post(f"/api/sessions/{session_id}/runs", json={"content": content, "request_id": request_id or str(uuid4())})
    assert response.status_code == 202, response.text
    return session_id, response.json()["id"]


def test_api_only_job_stays_pending_across_api_restart(app, queue_client):
    sid, rid = enqueue_run(queue_client)
    with TestClient(app, base_url="http://localhost:8000"):
        with app.state.session_factory() as db:
            assert db.get(Job, rid).state == "PENDING"
            assert db.get(WorkspaceRun, rid).status == "queued"
            assert db.get(SolveSession, sid).active_run_id == rid
            assert db.scalar(select(func.count()).select_from(ProviderCall)) == 0
    assert asyncio.run(Worker(app).run_once())
    assert queue_client.get(f"/api/runs/{rid}").json()["status"] == "completed"


def test_mock_worker_tools_trace_and_final_evaluation(app, queue_client):
    with app.state.session_factory.begin() as db:
        register_directory(db, ROOT / "examples/problems/workspace-plan")
    sid, rid = enqueue_run(queue_client, problem="workspace-plan", content="save a release plan")
    assert asyncio.run(Worker(app).run_once())
    with app.state.session_factory() as db:
        job = db.get(Job, rid)
        assert job.state == "COMPLETED" and job.attempt == 1
        assert job.claim_token is None and job.lease_expires_at is None
        assert not job.external_effect_uncertain
        assert "worker_id" not in job_public(job) and "claim_token" not in job_public(job)
    events = queue_client.get(f"/api/sessions/{sid}/trace").json()
    assert [e["sequence_number"] for e in events] == list(range(1, len(events) + 1))
    assert {"TOOL_CALL_REQUESTED", "TOOL_CALL_AUTHORIZED", "TOOL_CALL_COMPLETED", "ARTIFACT_UPDATED"} <= {e["event_type"] for e in events}
    files = queue_client.get(f"/api/sessions/{sid}/files").json()
    answer = next(f["content"] for f in files if f["path"] == "plan.txt")
    response = queue_client.post(f"/api/sessions/{sid}/submissions", json={"content": answer})
    assert response.status_code == 201, response.text
    result = queue_client.get(f"/api/evaluations/{response.json()['evaluation_id']}").json()
    assert result["score"] == result["maximum_score"] == 100


def test_enqueue_is_idempotent_and_conflicting_content_is_rejected(app, queue_client):
    key = str(uuid4())
    sid, rid = enqueue_run(queue_client, request_id=key)
    _, duplicate = enqueue_run(queue_client, request_id=key, session_id=sid)
    assert duplicate == rid
    assert queue_client.post(f"/api/sessions/{sid}/runs", json={"content": "different", "request_id": key}).status_code == 409
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 1
        assert db.scalar(select(func.count()).select_from(ConversationMessage)) == 1


@pytest.mark.parametrize("claimed", [False, True])
def test_cancel_fences_worker_and_cannot_clear_a_new_run(app, queue_client, claimed):
    sid, rid = enqueue_run(queue_client)
    repo = JobRepository(app.state.session_factory)
    lease = repo.claim("old-worker") if claimed else None
    cancelled = queue_client.post(f"/api/runs/{rid}/cancel", json={})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    _, fresh = enqueue_run(queue_client, session_id=sid, content="new request")
    with app.state.session_factory() as db:
        before = db.scalar(select(func.count()).select_from(TraceEvent))
    if lease:
        assert not RunManager(app, lease).finish(rid, "completed")
        assert not repo.heartbeat(lease)
        asyncio.run(RunManager(app, lease).execute(rid))
    with app.state.session_factory() as db:
        assert db.get(Job, rid).state == "CANCELLED"
        assert db.get(SolveSession, sid).active_run_id == fresh
        assert db.scalar(select(func.count()).select_from(TraceEvent)) == before


def test_expired_lease_preserves_unknown_usage_and_never_replays(app, queue_client):
    sid, rid = enqueue_run(queue_client)
    repo = JobRepository(app.state.session_factory)
    lease = repo.claim("crashed-worker")
    with app.state.session_factory.begin() as db:
        db.add(ProviderCall(session_id=sid, run_id=rid, status="started"))
        db.get(Job, rid).lease_expires_at = utcnow() - timedelta(seconds=1)
    assert not repo.heartbeat(lease)
    assert repo.recover() == 1
    assert repo.recover() == 0
    assert repo.claim("new-worker") is None
    assert not RunManager(app, lease).finish(rid, "completed")
    with app.state.session_factory() as db:
        job = db.get(Job, rid)
        assert job.state == "FAILED" and job.recovery_reason == "lease_expired"
        assert job.external_effect_uncertain
        call = db.scalar(select(ProviderCall).where(ProviderCall.run_id == rid))
        assert call.status == "failed" and call.input_tokens is None and call.output_tokens is None
        assert db.get(SolveSession, sid).active_run_id is None
    assert queue_client.get(f"/api/sessions/{sid}/usage").json()["usage_complete"] is False


def test_heartbeat_extends_only_matching_live_ownership(app, queue_client):
    _, rid = enqueue_run(queue_client)
    repo = JobRepository(app.state.session_factory)
    lease = repo.claim("worker")
    with app.state.session_factory.begin() as db:
        db.get(Job, rid).lease_expires_at = utcnow() + timedelta(seconds=2)
    assert repo.heartbeat(lease)
    assert not repo.heartbeat(replace(lease, claim_token="forged"))
    assert not repo.heartbeat(replace(lease, fence=lease.fence + 1))
    assert not repo.heartbeat(replace(lease, worker_id="other"))
    with app.state.session_factory() as db:
        assert aware(db.get(Job, rid).lease_expires_at) > utcnow() + timedelta(seconds=10)


def test_hard_deadline_overrides_a_live_lease(app, queue_client):
    _, rid = enqueue_run(queue_client)
    repo = JobRepository(app.state.session_factory)
    lease = repo.claim("worker")
    with app.state.session_factory.begin() as db:
        db.get(Job, rid).deadline_at = utcnow() - timedelta(seconds=1)
    assert not repo.heartbeat(lease)
    assert repo.recover() == 1
    with app.state.session_factory() as db:
        assert db.get(WorkspaceRun, rid).error["code"] == "job_timeout"


def test_lease_check_precedes_any_provider_or_tool_mutation(app, queue_client):
    _, rid = enqueue_run(queue_client)
    repo = JobRepository(app.state.session_factory)
    lease = repo.claim("worker")
    forged = replace(lease, fence=lease.fence + 1)
    with app.state.session_factory.begin() as db:
        with pytest.raises(LeaseLost):
            require_lease(db, forged)
    asyncio.run(RunManager(app, forged).execute(rid))
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ProviderCall)) == 0
        assert db.get(Job, rid).state == "RUNNING"


def test_future_scheduling_is_not_claimed_early(app, queue_client):
    _, rid = enqueue_run(queue_client)
    with app.state.session_factory.begin() as db:
        db.get(Job, rid).available_at = utcnow() + timedelta(hours=1)
    assert JobRepository(app.state.session_factory).claim("worker") is None


def test_expired_pending_session_never_calls_a_provider(app, queue_client):
    sid, rid = enqueue_run(queue_client)
    with app.state.session_factory.begin() as db:
        db.get(SolveSession, sid).trace_expires_at = utcnow() - timedelta(seconds=1)
    assert JobRepository(app.state.session_factory).claim("worker") is None
    with app.state.session_factory() as db:
        assert db.get(Job, rid).state == "FAILED"
        assert db.get(WorkspaceRun, rid).error["code"] == "session_expired"
        assert db.get(SolveSession, sid).active_run_id is None
        assert db.scalar(select(func.count()).select_from(ProviderCall)) == 0


def test_migration_quarantines_unowned_legacy_runs_with_trace(app, queue_client):
    sid, rid = enqueue_run(queue_client)
    with app.state.session_factory.begin() as db:
        db.get(WorkspaceRun, rid).status = "running"
        db.add(ProviderCall(session_id=sid, run_id=rid, status="started"))
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    command.downgrade(config, "0003_authentication")
    command.upgrade(config, "head")
    with app.state.session_factory() as db:
        assert db.get(WorkspaceRun, rid).error["code"] == "legacy_run_quarantined"
        assert db.get(WorkspaceRun, rid).status == "failed"
        assert db.get(SolveSession, sid).active_run_id is None
        call = db.scalar(select(ProviderCall).where(ProviderCall.run_id == rid))
        assert call.status == "failed" and call.input_tokens is None
        events = list(db.scalars(select(TraceEvent).where(TraceEvent.session_id == sid).order_by(TraceEvent.sequence_number)))
        assert [event.sequence_number for event in events] == list(range(1, len(events) + 1))
        assert events[-1].envelope["payload"]["reason"] == "legacy_run_quarantined"
    assert JobRepository(app.state.session_factory).claim("worker") is None


def test_heartbeat_keeps_a_slow_provider_call_owned(app, queue_client):
    app.state.settings = replace(app.state.settings, worker_lease_seconds=1, worker_heartbeat_seconds=.2)
    class SlowMock:
        async def respond(self, *args):
            await asyncio.sleep(2)
            return await AIRuntime(MockProvider()).respond(*args)
    app.state.runtime = SlowMock()
    _, rid = enqueue_run(queue_client)
    async def execute():
        worker = Worker(app)
        task = asyncio.create_task(worker.run_once())
        await asyncio.sleep(1.3)
        assert worker.repository.recover() == 0
        with app.state.session_factory() as db:
            assert db.get(Job, rid).state == "RUNNING"
        await task
    asyncio.run(execute())
    assert queue_client.get(f"/api/runs/{rid}").json()["status"] == "completed"


def test_worker_failure_logs_only_safe_codes(app, queue_client, monkeypatch, caplog):
    _, rid = enqueue_run(queue_client)
    def failure(*args, **kwargs):
        raise RuntimeError("private-database-password-value")
    monkeypatch.setattr(RunManager, "finish", failure)
    assert asyncio.run(Worker(app).run_once())
    assert "state_persistence_failed" in caplog.text
    assert "private-database-password-value" not in caplog.text
    with app.state.session_factory.begin() as db:
        db.get(Job, rid).lease_expires_at = utcnow() - timedelta(seconds=1)
    assert JobRepository(app.state.session_factory).recover() == 1


def require_postgres(app):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for real row locks and independent worker processes")


@pytest.mark.postgres
def test_two_workers_cannot_claim_the_same_job(app, queue_client):
    require_postgres(app)
    _, rid = enqueue_run(queue_client)
    barrier = threading.Barrier(2)
    def claim(name):
        barrier.wait(timeout=5)
        return JobRepository(app.state.session_factory).claim(name)
    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(claim, ["worker-a", "worker-b"]))
    assert sum(lease is not None for lease in leases) == 1
    assert next(lease for lease in leases if lease).run_id == rid


@pytest.mark.postgres
def test_skip_locked_allows_another_session_to_progress(app, queue_client):
    require_postgres(app)
    first_sid, first = enqueue_run(queue_client)
    _, second = enqueue_run(queue_client)
    with app.state.session_factory.begin() as db:
        db.scalar(select(SolveSession).where(SolveSession.id == first_sid).with_for_update())
        with ThreadPoolExecutor(max_workers=1) as pool:
            lease = pool.submit(JobRepository(app.state.session_factory).claim, "other-worker").result(timeout=5)
        assert lease.run_id == second
    assert JobRepository(app.state.session_factory).claim("first-worker").run_id == first


def worker_environment(database_url, **extra):
    # Only an explicit test endpoint is configured. Never inherit real provider keys.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PRAXIOJ_LLM_") and not k.startswith("PRAXIOJ_PRICE_")}
    env.update(DATABASE_URL=database_url, PRAXIOJ_ENV="test", PRAXIOJ_DEFAULT_PROFILE="mock",
               PRAXIOJ_WORKER_LEASE_SECONDS="1", PRAXIOJ_WORKER_HEARTBEAT_SECONDS="0.2", PRAXIOJ_WORKER_POLL_SECONDS="0.05")
    env.update(extra)
    return env


def worker_process(database_url, **extra):
    return subprocess.Popen([sys.executable, "-m", "praxioj_api.worker", "--once"], cwd=ROOT,
        env=worker_environment(database_url, **extra), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


@pytest.mark.postgres
def test_real_worker_processes_claim_once_and_complete(app, queue_client, database_url):
    require_postgres(app)
    _, rid = enqueue_run(queue_client)
    processes = [worker_process(database_url), worker_process(database_url)]
    try:
        for process in processes:
            _, error = process.communicate(timeout=15)
            assert process.returncode == 0, error
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
    with app.state.session_factory() as db:
        assert db.get(Job, rid).state == "COMPLETED"
        assert db.get(Job, rid).attempt == 1
        assert db.scalar(select(func.count()).select_from(ProviderCall)) == 1


@pytest.mark.postgres
def test_real_worker_with_local_tool_provider_and_evaluation(database_url):
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL required for independent API/worker fixture integration")
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            if len(requests) == 1:
                message = {"role": "assistant", "content": None, "tool_calls": [{"id": "local-tool-call", "type": "function",
                    "function": {"name": "write_file", "arguments": json.dumps({"path": "plan.txt", "content": "Goal Verification Risk"})}}]}
            else:
                message = {"role": "assistant", "content": "Created the plan."}
            body = json.dumps({"id": "local-fixture", "choices": [{"message": message}],
                               "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/v1"
    app = create_app(Settings(database_url=database_url, environment="test", llm_base_url=url,
                              llm_model="local/fixture", llm_supports_tools=True))
    with app.state.session_factory.begin() as db:
        register_directory(db, ROOT / "examples/problems/workspace-plan")
    process = None
    try:
        with TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as client:
            authenticate_client(client)
            sid, rid = enqueue_run(client, problem="workspace-plan", content="save plan", profile="compatible")
            process = worker_process(database_url, PRAXIOJ_LLM_BASE_URL=url, PRAXIOJ_LLM_MODEL="local/fixture",
                                     PRAXIOJ_LLM_SUPPORTS_TOOLS="true")
            _, error = process.communicate(timeout=15)
            assert process.returncode == 0, error
            assert client.get(f"/api/runs/{rid}").json()["status"] == "completed"
            assert [message["role"] for message in requests[1]["messages"]] == ["user", "assistant", "tool"]
            answer = next(f["content"] for f in client.get(f"/api/sessions/{sid}/files").json() if f["path"] == "plan.txt")
            receipt = client.post(f"/api/sessions/{sid}/submissions", json={"content": answer}).json()
            result = client.get(f"/api/evaluations/{receipt['evaluation_id']}").json()
            assert result["score"] == result["maximum_score"] == 100
            usage = client.get(f"/api/sessions/{sid}/usage").json()
            assert usage["input_tokens"] == 20 and usage["output_tokens"] == 10 and usage["usage_complete"]
            events = client.get(f"/api/sessions/{sid}/trace").json()
            assert any(event["event_type"] == "TOOL_CALL_AUTHORIZED" and event["payload"]["allowed"] for event in events)
            assert any(event["event_type"] == "EVALUATION_COMPLETED" for event in events)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        app.state.engine.dispose()


@pytest.mark.postgres
def test_killed_process_lease_is_recovered_without_second_provider_request(database_url):
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL required for process crash verification")
    started, release = threading.Event(), threading.Event()
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            started.set()
            release.wait(10)
            body = json.dumps({"id": "local-delayed", "choices": [{"message": {"role": "assistant", "content": "Late response"}}]}).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/v1"
    app = create_app(Settings(database_url=database_url, environment="test", llm_base_url=url, llm_model="local/fixture"))
    with app.state.session_factory.begin() as db:
        register_directory(db, ROOT / "examples/problems/release-plan")
    process = None
    try:
        with TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as client:
            authenticate_client(client)
            _, rid = enqueue_run(client, profile="compatible")
            extra = {"PRAXIOJ_LLM_BASE_URL": url, "PRAXIOJ_LLM_MODEL": "local/fixture"}
            process = worker_process(database_url, **extra)
            assert started.wait(10), "Worker did not call local fixture"
            process.kill()
            process.communicate(timeout=5)
            release.set()
            time.sleep(1.2)
            recovered = worker_process(database_url, **extra)
            try:
                _, error = recovered.communicate(timeout=10)
                assert recovered.returncode == 0, error
            finally:
                if recovered.poll() is None:
                    recovered.kill()
                    recovered.wait()
            assert len(calls) == 1
            with app.state.session_factory() as db:
                job = db.get(Job, rid)
                assert job.state == "FAILED" and job.recovery_reason == "lease_expired"
                assert job.external_effect_uncertain
                call = db.scalar(select(ProviderCall).where(ProviderCall.run_id == rid))
                assert call.status == "failed" and call.input_tokens is None
    finally:
        release.set()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        app.state.engine.dispose()
