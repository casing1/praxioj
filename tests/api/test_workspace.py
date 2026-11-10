"""M2 application tests require no credentials and never call external providers."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import threading
import time
from uuid import uuid4
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient
from conftest import authenticate_client
from worker_support import worker_thread
import pytest
from sqlalchemy import select

from praxioj.problems import ProblemManifest, load_problem_package
from praxioj.runtime import AIRuntime, MockProvider, ProviderError, ProviderResponse, ToolCall, Usage
from praxioj_api.main import create_app
from praxioj_api.models import ConversationMessage, ProviderCall, SolveSession, Submission, WorkspaceRun
from praxioj_api.models import utcnow
from praxioj_api.job_models import Job
from praxioj_api.jobs import JobRepository
from praxioj_api.runs import RunManager
from praxioj_api.worker import Worker
from praxioj_api.registry import register_manifest
from praxioj_api.settings import Settings

ROOT = Path(__file__).resolve().parents[2]


def register_workspace(app, **updates):
    data = load_problem_package(ROOT / "examples/problems/workspace-plan").model_dump(mode="json")
    data.update(updates)
    with app.state.session_factory.begin() as db:
        register_manifest(db, ProblemManifest.model_validate(data))
    return data


def new_session(client, problem="workspace-plan", version="1.0.0", **extra):
    response = client.post("/api/sessions", json={"problem_id": problem, "version": version, **extra})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def start(client, sid, content="save a release plan", request_id=None):
    response = client.post(f"/api/sessions/{sid}/runs", json={"content": content, "request_id": request_id or str(uuid4())})
    assert response.status_code == 202, response.text
    return response.json()


def wait_run(client, rid):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{rid}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] not in {"queued", "running"}:
            return run
        time.sleep(.01)
    pytest.fail("Run did not finish within test deadline")


def test_tool_session_complete_flow_and_frozen_artifacts(app, client):
    register_workspace(app)
    sid = new_session(client)
    run = wait_run(client, start(client, sid)["id"])
    assert run["status"] == "completed", run
    detail = client.get(f"/api/sessions/{sid}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "tool", "assistant"]
    assert detail["active_run_id"] is None and detail["latest_run"]["id"] == run["id"]
    files = client.get(f"/api/sessions/{sid}/files").json()
    plan = next(f for f in files if f["path"] == "plan.txt")
    assert plan["sha256"] == sha256(plan["content"].encode()).hexdigest()
    assert client.put(f"/api/sessions/{sid}/draft", json={"content": plan["content"]}).json()["content"] == plan["content"]
    assert client.get(f"/api/sessions/{sid}").json()["draft"] == plan["content"]
    usage = client.get(f"/api/sessions/{sid}/usage").json()
    assert usage["model_calls"] == 2 and usage["tool_calls"] == 1
    assert usage["estimated"] and usage["usage_complete"] and usage["cost_estimate"] is None
    events = client.get(f"/api/sessions/{sid}/trace").json()
    kinds = [e["event_type"] for e in events]
    for kind in ["PROVIDER_CALL_STARTED", "PROVIDER_CALL_COMPLETED", "TOOL_CALL_REQUESTED", "TOOL_CALL_AUTHORIZED", "TOOL_CALL_COMPLETED", "ARTIFACT_UPDATED"]:
        assert kind in kinds
    assert [e["sequence_number"] for e in events] == list(range(1, len(events) + 1))
    assert all(e["correlation_id"] == run["id"] for e in events[1:])
    calls = [e for e in events if e["event_type"] == "TOOL_CALL_COMPLETED"]
    assert calls[0]["payload"]["status"] == "completed"
    captured = []
    original = app.state.evaluator
    class Capture:
        def evaluate(self, request):
            captured.append(request)
            return original.evaluate(request)
    app.state.evaluator = Capture()
    receipt = client.post(f"/api/sessions/{sid}/submissions", json={"content": plan["content"]})
    assert receipt.status_code == 201
    assert client.get(f"/api/evaluations/{receipt.json()['evaluation_id']}").json()["score"] == 100
    assert any(a.sha256 == plan["sha256"] for a in captured[0].artifacts)
    with app.state.session_factory() as db:
        frozen = db.scalar(select(Submission).where(Submission.session_id == sid)).artifacts
        assert any(a["path"] == "plan.txt" and a["sha256"] == plan["sha256"] for a in frozen)


def test_run_idempotency_and_changed_content_conflict(app, client):
    register_workspace(app)
    sid = new_session(client)
    key = str(uuid4())
    run = wait_run(client, start(client, sid, request_id=key)["id"])
    before = client.get(f"/api/sessions/{sid}/trace").json()
    assert start(client, sid, request_id=key)["id"] == run["id"]
    assert client.post(f"/api/sessions/{sid}/runs", json={"content": "changed", "request_id": key}).status_code == 409
    assert client.get(f"/api/sessions/{sid}/trace").json() == before
    assert len(client.get(f"/api/sessions/{sid}/runs").json()) == 1
    assert len([f for f in client.get(f"/api/sessions/{sid}/files").json() if f["path"] == "plan.txt"]) == 1


def test_sessions_and_new_routes_are_owner_scoped(app, client):
    register_workspace(app)
    sid = new_session(client)
    rid = start(client, sid)["id"]
    wait_run(client, rid)
    second = new_session(client)
    assert all(f["path"] != "plan.txt" for f in client.get(f"/api/sessions/{second}/files").json())
    # Another authenticated account cannot access this owner's workspace.
    stranger = TestClient(app, base_url="http://localhost:8000")
    authenticate_client(stranger)
    for suffix in ["", "/files", "/usage", "/runs", "/trace"]:
        assert stranger.get(f"/api/sessions/{sid}{suffix}").status_code == 404
    assert stranger.get(f"/api/runs/{rid}").status_code == 404
    assert stranger.post(f"/api/runs/{rid}/cancel", json={}).status_code == 404
    assert stranger.put(f"/api/sessions/{sid}/draft", json={"content": "stolen"}).status_code == 404
    assert stranger.post(f"/api/sessions/{sid}/end", json={}).status_code == 404


def test_cancel_conflicts_and_accounting(app, client, session):
    entered = threading.Event()
    class SlowRuntime:
        async def respond(self, *_args):
            entered.set()
            await asyncio.sleep(30)
    app.state.runtime = SlowRuntime()
    sid = session["id"]
    rid = start(client, sid, "slow")["id"]
    assert entered.wait(2)
    for path, body in [("runs", {"content": "second", "request_id": str(uuid4())}), ("messages", {"content": "second"}),
                       ("submissions", {"content": "Goal"}), ("end", {})]:
        assert client.post(f"/api/sessions/{sid}/{path}", json=body).status_code == 409
    assert client.post(f"/api/runs/{rid}/cancel", json={}).json()["status"] == "cancelled"
    assert wait_run(client, rid)["error"]["code"] == "cancelled"
    usage = client.get(f"/api/sessions/{sid}/usage").json()
    assert usage["model_calls"] == 1 and not usage["usage_complete"]
    assert client.get(f"/api/sessions/{sid}").json()["active_run_id"] is None
    app.state.runtime = AIRuntime(MockProvider())
    assert wait_run(client, start(client, sid, "continue")["id"])["status"] == "completed"


def test_failed_provider_is_safe_and_attempt_counts(app, client, session, caplog):
    class Broken:
        async def respond(self, *_args):
            raise RuntimeError("private-credentials-should-never-appear")
    app.state.runtime = Broken()
    sid = session["id"]
    run = wait_run(client, start(client, sid, "Help")["id"])
    assert run["status"] == "failed"
    trace = client.get(f"/api/sessions/{sid}/trace").text
    assert "private-credentials" not in trace + caplog.text + json.dumps(run)
    assert client.get(f"/api/sessions/{sid}/usage").json()["model_calls"] == 1
    assert client.get(f"/api/sessions/{sid}").json()["messages"][0]["role"] == "user"


@pytest.mark.parametrize("limits,expected", [({"max_model_calls": 1}, "model_call_limit"),
                                               ({"max_tool_calls": 0}, "tool_call_limit")])
def test_hard_loop_limits(app, client, limits, expected):
    data = load_problem_package(ROOT / "examples/problems/workspace-plan").model_dump(mode="json")
    register_workspace(app, resource_limits={**data["resource_limits"], **limits})
    sid = new_session(client)
    run = wait_run(client, start(client, sid)["id"])
    assert run["error"]["code"] == expected
    usage = client.get(f"/api/sessions/{sid}/usage").json()
    assert usage["model_calls"] == 1
    assert usage["tool_calls"] <= limits.get("max_tool_calls", 20)


def test_permissions_checked_before_mutation(app, client):
    register_workspace(app, tool_permissions=["workspace:read"])
    sid = new_session(client)
    run = wait_run(client, start(client, sid)["id"])
    assert run["status"] == "completed"
    assert all(f["path"] != "plan.txt" for f in client.get(f"/api/sessions/{sid}/files").json())
    events = client.get(f"/api/sessions/{sid}/trace").json()
    auth = next(e for e in events if e["event_type"] == "TOOL_CALL_AUTHORIZED")
    assert auth["payload"]["code"] == "permission_denied" and not auth["payload"]["allowed"]


def test_timeout_and_unknown_usage_token_budget(app, client):
    data = load_problem_package(ROOT / "examples/problems/workspace-plan").model_dump(mode="json")
    register_workspace(app, resource_limits={**data["resource_limits"], "request_timeout_seconds": 1, "max_total_tokens": 500})
    class Slow:
        async def respond(self, *_args):
            await asyncio.sleep(30)
    app.state.runtime = Slow()
    sid = new_session(client)
    run = wait_run(client, start(client, sid, "slow")["id"])
    assert run["error"]["code"] == "provider_timeout"
    response = client.post(f"/api/sessions/{sid}/runs", json={"content": "retry", "request_id": str(uuid4())})
    assert response.status_code == 429 and response.json()["detail"] == "usage_unknown"


def test_ended_session_cannot_resume_or_submit(client, session):
    sid = session["id"]
    assert client.post(f"/api/sessions/{sid}/end", json={}).json()["status"] == "ended"
    assert client.post(f"/api/sessions/{sid}/submissions", json={"content": "Goal"}).status_code == 409
    assert client.post(f"/api/sessions/{sid}/runs", json={"content": "Hi", "request_id": str(uuid4())}).status_code == 409
    assert client.put(f"/api/sessions/{sid}/draft", json={"content": "draft"}).status_code == 409


def test_recovery_marks_abandoned_runs_without_replaying(app, client, session):
    sid = session["id"]
    with app.state.session_factory.begin() as db:
        row = db.get(SolveSession, sid)
        run = WorkspaceRun(session_id=sid, request_id=str(uuid4()), content_sha256="a" * 64, status="running")
        db.add(run)
        db.flush()
        rid = run.id
        row.active_run_id = rid
        db.add(ProviderCall(session_id=sid, run_id=rid))
        db.add(Job(run_id=rid, session_id=sid, state="RUNNING", max_seconds=90,
                   worker_id="crashed-test-worker", claim_token="synthetic", fence=1, attempt=1,
                   lease_expires_at=utcnow() - timedelta(seconds=1), deadline_at=utcnow() + timedelta(seconds=60)))
    JobRepository(app.state.session_factory).recover()
    recovered = client.get(f"/api/runs/{rid}").json()
    assert recovered["status"] == "failed" and recovered["error"]["code"] == "lease_expired"
    assert client.get(f"/api/sessions/{sid}").json()["active_run_id"] is None
    assert not client.get(f"/api/sessions/{sid}/usage").json()["usage_complete"]


@pytest.fixture
def local_provider():
    requests = []
    responses = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            response = responses.pop(0)
            self.send_response(response.get("status", 200))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response["body"]).encode())
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1", requests, responses
    server.shutdown()
    server.server_close()
    thread.join()


def wire_reply(message, usage=None):
    body = {"id": "local-test-response", "model": "local/test-model", "choices": [{"message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}]}
    if usage is not None:
        body["usage"] = usage
    return {"body": body}


def test_local_http_provider_tool_loop_context_prices_and_redaction(database_url, local_provider):
    url, requests, responses = local_provider
    settings = Settings(database_url=database_url, environment="test", llm_base_url=url, llm_model="local/test-model",
        llm_api_key="synthetic-local-test-credential", llm_supports_tools=True,
        price_input_per_million=2, price_output_per_million=8)
    app = create_app(settings)
    register_workspace(app)
    responses.extend([
        wire_reply({"role": "assistant", "content": None, "tool_calls": [{"id": "call-one", "type": "function", "function": {
            "name": "write_file", "arguments": json.dumps({"path": "plan.txt", "content": "Goal Verification Risk synthetic-local-test-credential"})}}]}, {"prompt_tokens": 20, "completion_tokens": 10}),
        wire_reply({"role": "assistant", "content": "Saved synthetic-local-test-credential"}, {"prompt_tokens": 40, "completion_tokens": 5}),
        wire_reply({"role": "assistant", "content": "Follow up"}),
    ])
    with worker_thread(app), TestClient(app, base_url="http://localhost:8000") as client:
        authenticate_client(client)
        options = client.get("/api/runtime/options").json()
        assert len(options["profiles"]) == 2 and url not in json.dumps(options)
        sid = new_session(client, runtime_profile="compatible")
        assert client.post(f"/api/sessions/{sid}/messages", json={"content": "legacy"}).status_code == 409
        assert wait_run(client, start(client, sid)["id"])["status"] == "completed"
        assert [m["role"] for m in requests[1]["messages"]] == ["user", "assistant", "tool"]
        assert requests[1]["messages"][-1]["tool_call_id"] == "call-one"
        usage = client.get(f"/api/sessions/{sid}/usage").json()
        assert usage["input_tokens"] == 60 and usage["output_tokens"] == 15
        assert usage["cost_estimate"] == pytest.approx(.00024) and usage["cost_estimate_complete"]
        assert not usage["estimated"]
        for endpoint in [f"/api/sessions/{sid}", f"/api/sessions/{sid}/trace", f"/api/sessions/{sid}/files"]:
            assert "synthetic-local-test-credential" not in client.get(endpoint).text
        assert wait_run(client, start(client, sid, "Continue")["id"])["status"] == "completed"
        assert [m["role"] for m in requests[2]["messages"]] == ["user", "assistant", "tool", "assistant", "user"]
        usage = client.get(f"/api/sessions/{sid}/usage").json()
        assert not usage["usage_complete"] and not usage["cost_estimate_complete"]
        assert usage["input_tokens"] == 60


def test_submission_preserves_unsaved_answer_in_closed_workspace(client, session):
    sid = session["id"]
    client.put(f"/api/sessions/{sid}/draft", json={"content": "old draft"})
    answer = "Goal: release. Verification: tests. Risk: regressions."
    assert client.post(f"/api/sessions/{sid}/submissions", json={"content": answer}).status_code == 201
    detail = client.get(f"/api/sessions/{sid}").json()
    assert detail["draft"] == answer and detail["status"] == "submitted"


def test_denied_tool_limit_preserves_tool_history_and_traces(app, client):
    data = load_problem_package(ROOT / "examples/problems/workspace-plan").model_dump(mode="json")
    register_workspace(app, resource_limits={**data["resource_limits"], "max_tool_calls": 0})
    sid = new_session(client)
    run = wait_run(client, start(client, sid)["id"])
    assert run["error"]["code"] == "tool_call_limit"
    events = client.get(f"/api/sessions/{sid}/trace").json()
    tool_events = [e for e in events if e["event_type"].startswith("TOOL_CALL_")]
    assert [e["event_type"] for e in tool_events] == ["TOOL_CALL_REQUESTED", "TOOL_CALL_AUTHORIZED", "TOOL_CALL_COMPLETED"]
    assert not tool_events[1]["payload"]["allowed"]
    assert tool_events[2]["payload"]["content"]["executed"] is False
    messages = client.get(f"/api/sessions/{sid}").json()["messages"]
    assert messages[-1]["tool_call_id"] == messages[-2]["tool_calls"][0]["id"]
    assert client.get(f"/api/sessions/{sid}/usage").json()["tool_calls"] == 0


def test_background_persistence_failure_never_logs_exception_content(app, monkeypatch, caplog):
    original = RunManager.finish
    def failing_finish(*_args):
        raise RuntimeError("private-sql-params-and-credentials")
    monkeypatch.setattr(RunManager, "finish", failing_finish)
    # Own one explicit worker invocation. A log message is not a completion
    # barrier: a background worker may still be reconciling in another transaction.
    with TestClient(app, base_url="http://localhost:8000") as client:
        authenticate_client(client)
        sid = new_session(client, problem="release-plan")
        rid = start(client, sid, "hello")["id"]
        assert asyncio.run(Worker(app).run_once())
        assert "state_persistence_failed" in caplog.text
        assert "private-sql-params" not in caplog.text
        assert client.get(f"/api/runs/{rid}").json()["status"] == "running"
        monkeypatch.setattr(RunManager, "finish", original)
        with app.state.session_factory.begin() as db:
            db.get(Job, rid).lease_expires_at = utcnow() - timedelta(seconds=1)
        assert JobRepository(app.state.session_factory).recover() == 1
        recovered = client.get(f"/api/runs/{rid}").json()
        assert recovered["status"] == "failed" and recovered["error"]["code"] == "lease_expired"


@pytest.mark.postgres
def test_competing_recovery_skips_a_transition_until_its_owner_commits(app, monkeypatch):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL required to verify SKIP LOCKED recovery visibility")
    from praxioj_api import jobs
    entered, release = threading.Event(), threading.Event()
    terminalize = jobs.terminalize
    def paused_terminalize(*args, **kwargs):
        entered.set()
        assert release.wait(5), "Recovery transition was not released"
        return terminalize(*args, **kwargs)
    monkeypatch.setattr(jobs, "terminalize", paused_terminalize)
    with TestClient(app, base_url="http://localhost:8000") as client:
        authenticate_client(client)
        sid = new_session(client, problem="release-plan")
        rid = start(client, sid, "hello")["id"]
        repository = JobRepository(app.state.session_factory)
        assert repository.claim("recovery-test-worker") is not None
        with app.state.session_factory.begin() as db:
            db.get(Job, rid).lease_expires_at = utcnow() - timedelta(seconds=1)
        with ThreadPoolExecutor(max_workers=1) as executor:
            transition = executor.submit(repository.recover)
            try:
                assert entered.wait(5), "Recovery did not acquire its locks"
                # Another reconciler cannot claim completion of an in-flight
                # transition: it skips the lock and readers see committed state.
                assert repository.recover() == 0
                pending = client.get(f"/api/runs/{rid}").json()
                assert pending["status"] == "running" and pending["error"] is None
            finally:
                release.set()
            assert transition.result(timeout=5) == 1
        recovered = client.get(f"/api/runs/{rid}").json()
        assert recovered["status"] == "failed" and recovered["error"]["code"] == "lease_expired"


def test_elapsed_run_budget_stops_further_tool_mutations(app, client, monkeypatch):
    from praxioj_api import runs
    data = load_problem_package(ROOT / "examples/problems/workspace-plan").model_dump(mode="json")
    register_workspace(app, resource_limits={**data["resource_limits"], "max_run_seconds": 1})
    sid = new_session(client)
    real = runs.monotonic
    now = real()
    ticks = iter([now, now, now + 2])
    monkeypatch.setattr(runs, "monotonic", lambda: next(ticks, now + 2))
    run = wait_run(client, start(client, sid)["id"])
    assert run["error"]["code"] == "run_timeout"
    assert all(f["path"] != "plan.txt" for f in client.get(f"/api/sessions/{sid}/files").json())


def test_adapter_error_metadata_is_safe_and_traceable(app, client, session, caplog):
    class Rejected:
        async def respond(self, *_args):
            raise ProviderError("upstream-private-error-body", code="provider_http_error", retryable=True, http_status=429)
    app.state.runtime = Rejected()
    sid = session["id"]
    run = wait_run(client, start(client, sid, "help")["id"])
    assert run["error"]["code"] == "provider_http_error"
    events = client.get(f"/api/sessions/{sid}/trace").json()
    result = next(e for e in events if e["event_type"] == "PROVIDER_CALL_COMPLETED")
    assert result["payload"]["http_status"] == 429 and result["payload"]["retryable"]
    assert "http_status=429" in caplog.text
    assert "upstream-private-error-body" not in caplog.text + json.dumps(events)


def tool_wire_reply(content, call_id="call_0"):
    return wire_reply({"role": "assistant", "content": None, "tool_calls": [{
        "id": call_id, "type": "function", "function": {"name": "write_file", "arguments": json.dumps({
            "path": "plan.txt", "content": content})}}]})


@pytest.mark.parametrize("within_run", [False, True])
def test_tool_ids_may_repeat_across_runs_but_never_execute_twice_within_run(database_url, local_provider, within_run):
    url, requests, responses = local_provider
    app = create_app(Settings(database_url=database_url, environment="test", llm_base_url=url,
        llm_model="local/test-model", llm_supports_tools=True))
    register_workspace(app)
    responses.append(tool_wire_reply("first write"))
    if not within_run:
        responses.append(wire_reply({"role": "assistant", "content": "First run complete"}))
    responses.append(tool_wire_reply("second write"))
    if not within_run:
        responses.append(wire_reply({"role": "assistant", "content": "Second run complete"}))
    with worker_thread(app), TestClient(app, base_url="http://localhost:8000") as client:
        authenticate_client(client)
        sid = new_session(client, runtime_profile="compatible")
        first = wait_run(client, start(client, sid)["id"])
        if within_run:
            assert first["status"] == "failed" and first["error"]["code"] == "duplicate_tool_call"
        else:
            assert first["status"] == "completed", first
            second = wait_run(client, start(client, sid, "save a release plan again")["id"])
            assert second["status"] == "completed", second
            assert [m["role"] for m in requests[-1]["messages"]] == [
                "user", "assistant", "tool", "assistant", "user", "assistant", "tool"]
        plan = next(f for f in client.get(f"/api/sessions/{sid}/files").json() if f["path"] == "plan.txt")
        assert plan["content"] == ("first write" if within_run else "second write")
        assert plan["revision"] == (1 if within_run else 2)
        usage = client.get(f"/api/sessions/{sid}/usage").json()
        assert usage["tool_calls"] == (1 if within_run else 2)
        events = client.get(f"/api/sessions/{sid}/trace").json()
        executions = [e for e in events if e["event_type"] == "TOOL_CALL_COMPLETED"]
        assert len(executions) == (1 if within_run else 2)


def test_stopped_new_run_reused_tool_id_gets_its_own_denied_result(database_url, local_provider):
    url, _, responses = local_provider
    app = create_app(Settings(database_url=database_url, environment="test", llm_base_url=url,
        llm_model="local/test-model", llm_supports_tools=True))
    data = load_problem_package(ROOT / "examples/problems/workspace-plan").model_dump(mode="json")
    register_workspace(app, resource_limits={**data["resource_limits"], "max_tool_calls": 1})
    responses.extend([tool_wire_reply("first write"), wire_reply({"role": "assistant", "content": "Done"}),
                      tool_wire_reply("must not write")])
    with worker_thread(app), TestClient(app, base_url="http://localhost:8000") as client:
        authenticate_client(client)
        sid = new_session(client, runtime_profile="compatible")
        assert wait_run(client, start(client, sid)["id"])["status"] == "completed"
        second = wait_run(client, start(client, sid, "again")["id"])
        assert second["error"]["code"] == "tool_call_limit"
        messages = client.get(f"/api/sessions/{sid}").json()["messages"]
        assert messages[-1]["role"] == "tool" and messages[-1]["tool_call_id"] == "call_0"
        assert json.loads(messages[-1]["content"])["content"]["executed"] is False
        events = client.get(f"/api/sessions/{sid}/trace").json()
        result = [e for e in events if e["event_type"] == "TOOL_CALL_COMPLETED"][-1]
        assert result["correlation_id"] == second["id"] and result["payload"]["status"] == "denied"
