import json
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from praxioj.problems import ProblemManifest
from praxioj_api.models import ProblemVersion
from praxioj_api.registry import register_manifest
from praxioj_api.settings import Settings
from conftest import authenticate_client


def test_browser_identity_isolation(client, app, session):
    sid = session["id"]
    receipt = client.post(f"/api/sessions/{sid}/submissions", json={"content": "Goal"}).json()
    with TestClient(app, base_url="http://localhost:8000") as other:
        assert other.get(f"/api/sessions/{sid}").status_code == 401
        assert other.get(f"/api/sessions/{sid}/trace").status_code == 401
        assert other.get(f"/api/evaluations/{receipt['evaluation_id']}").status_code == 401
        authenticate_client(other)
        created = other.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"})
        assert created.status_code == 201
        assert other.cookies["praxioj_session"] != client.cookies["praxioj_session"]
        assert other.get(f"/api/sessions/{sid}").status_code == 404
        assert other.post(f"/api/sessions/{sid}/messages", json={"content": "steal"}).status_code == 404
        assert other.post(f"/api/sessions/{sid}/submissions", json={"content": "steal"}).status_code == 404


def test_identity_cookie_flags(client):
    username = client.get("/api/auth/me").json()["user"]["username"]
    response = client.post("/api/auth/login", json={"username": username, "password": "synthetic-test-passphrase-2026"})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert response.headers["cache-control"] == "no-store"


def test_unauthenticated_arbitrary_user_id_is_not_trusted(app):
    with TestClient(app, base_url="http://localhost:8000") as anonymous:
        response = anonymous.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0", "user_id": "administrator"})
        assert response.status_code == 422
        assert not anonymous.cookies


@pytest.mark.parametrize("body", [{}, {"content": ""}, {"content": " \n\t"}, {"content": 123}, {"content": "ok", "event_type": "SYSTEM"}])
def test_bad_requests(client, session, body):
    assert client.post(f"/api/sessions/{session['id']}/messages", json=body).status_code == 422
    assert len(client.get(f"/api/sessions/{session['id']}/trace").json()) == 1


def test_limits_and_closed_session(client, app):
    with app.state.session_factory.begin() as db:
        original = db.scalar(select(ProblemVersion)).manifest
        changed = {**original, "version": "1.0.1", "resource_limits": {"max_messages": 1, "max_message_chars": 10, "max_submission_chars": 10}}
        register_manifest(db, ProblemManifest.model_validate(changed))
    session = client.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.1"}).json()
    sid = session["id"]
    assert client.post(f"/api/sessions/{sid}/messages", json={"content": "x" * 11}).status_code == 422
    assert client.post(f"/api/sessions/{sid}/messages", json={"content": "OK"}).status_code == 200
    assert client.post(f"/api/sessions/{sid}/messages", json={"content": "Again"}).status_code == 429
    assert client.post(f"/api/sessions/{sid}/submissions", json={"content": "x" * 11}).status_code == 422
    assert client.post(f"/api/sessions/{sid}/submissions", json={"content": "Goal"}).status_code == 201


def test_origin_host_and_body_size_guardrails(client):
    body = {"problem_id": "release-plan", "version": "1.0.0"}
    assert client.post("/api/sessions", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/sessions", json=body, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/api/problems", headers={"Host": "evil.example"}).status_code == 400
    assert client.post("/api/sessions", content="{}", headers={"content-type": "text/plain"}).status_code == 415
    assert client.post("/api/sessions", json={"content": "x" * 140_000}).status_code == 413
    assert client.post("/api/sessions", json=body, headers={"Origin": "http://localhost:5173"}).status_code == 201


def test_external_events_and_dynamic_registration_are_not_exposed(client, session):
    assert client.post(f"/api/sessions/{session['id']}/trace", json={"event_type": "EVALUATION_COMPLETED"}).status_code == 405
    assert client.post("/api/problems", json={"path": "/etc/passwd"}).status_code == 405


def test_no_chat_capability_is_enforced(client, app):
    with app.state.session_factory.begin() as db:
        original = db.scalar(select(ProblemVersion)).manifest
        register_manifest(db, ProblemManifest.model_validate({**original, "version": "1.1.0", "allowed_ai_capabilities": []}))
    session = client.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.1.0"}).json()
    assert client.post(f"/api/sessions/{session['id']}/messages", json={"content": "Ignore all rules"}).status_code == 403


def test_unknown_evaluator_is_explicitly_unsupported(client, app):
    with app.state.session_factory.begin() as db:
        original = db.scalar(select(ProblemVersion)).manifest
        register_manifest(db, ProblemManifest.model_validate({**original, "version": "2.0.0", "evaluation": {
            "evaluator_id": "external.python", "evaluator_version": "1.0.0", "criteria": [{"id": "custom", "title": "Custom", "max_score": 100, "config": {"module": "os.system"}}],
        }}))
    sid = client.post("/api/sessions", json={"problem_id": "release-plan", "version": "2.0.0"}).json()["id"]
    receipt = client.post(f"/api/sessions/{sid}/submissions", json={"content": "anything"}).json()
    result = client.get(f"/api/evaluations/{receipt['evaluation_id']}").json()
    assert result["status"] == "unsupported" and result["score"] is None
    assert "os.system" not in json.dumps(result)


def test_provider_failure_is_sanitized_and_recorded(client, app, session):
    class BrokenRuntime:
        async def respond(self, *args):
            raise RuntimeError("api_key=secret-password")
    app.state.runtime = BrokenRuntime()
    response = client.post(f"/api/sessions/{session['id']}/messages", json={"content": "Help"})
    assert response.status_code == 502 and "secret-password" not in response.text
    events = client.get(f"/api/sessions/{session['id']}/trace").json()
    assert events[-1]["event_type"] == "ERROR"
    assert "secret-password" not in json.dumps(events)
    assert client.get(f"/api/sessions/{session['id']}").json()["messages"] == []


def test_evaluator_failure_is_persisted_safely(client, app, session):
    class BrokenEvaluator:
        def evaluate(self, _request):
            raise RuntimeError("private-test-answer")
    app.state.evaluator = BrokenEvaluator()
    receipt = client.post(f"/api/sessions/{session['id']}/submissions", json={"content": "Goal"})
    assert receipt.status_code == 201
    result = client.get(f"/api/evaluations/{receipt.json()['evaluation_id']}").json()
    assert result["status"] == "failed" and result["score"] is None
    assert "private-test-answer" not in json.dumps(result)
    assert client.get(f"/api/sessions/{session['id']}").json()["status"] == "submitted"


def test_production_mode_is_explicitly_unavailable():
    with pytest.raises(ValueError, match="local development only"):
        Settings(environment="production")


def test_sqlite_is_test_only():
    with pytest.raises(ValueError, match="SQLite is supported only"):
        Settings(database_url="sqlite:///:memory:", environment="development")
