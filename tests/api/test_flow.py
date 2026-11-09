from datetime import datetime
from hashlib import sha256
import json

from fastapi.testclient import TestClient
from sqlalchemy import select
from praxioj_api.models import ConversationMessage, Submission, User


def test_health_and_public_problem_projection(client):
    assert client.get("/api/health").json() == {"status": "ok", "mode": "local-development", "provider": "mock"}
    problems = client.get("/api/problems").json()
    assert len(problems) == 1
    problem = client.get("/api/problems/release-plan?version=1.0.0").json()
    assert problem == problems[0]
    assert problem["version"] == "1.0.0"
    assert "required_terms" not in json.dumps(problem)
    assert "config" not in problem["evaluation"]["criteria"][0]
    assert client.get("/api/problems/missing").status_code == 404
    assert client.get("/api/problems/release-plan?version=9.0.0").status_code == 404


def test_complete_persisted_solve_flow(client, app, session):
    session_id = session["id"]
    assert session["messages"] == [] and session["status"] == "active"
    assert client.get(f"/api/sessions/{session_id}").json() == session
    cookie = client.cookies["praxioj_dev_identity"]
    with app.state.session_factory() as db:
        identity = db.scalar(select(User))
        assert identity.identity_token_hash == sha256(cookie.encode()).hexdigest()
        assert identity.identity_token_hash != cookie
        assert identity.role == "participant"
    chat = client.post(f"/api/sessions/{session_id}/messages", json={"content": "Help me plan a release"})
    assert chat.status_code == 200, chat.text
    assert chat.json()["user_message"]["content"] == "Help me plan a release"
    assert "mock" in chat.json()["assistant_message"]["content"].lower()
    content = "Goal: ship a working release. Verification: run all tests. Risk: undocumented setup; mitigate with a clean install."
    submitted = client.post(f"/api/sessions/{session_id}/submissions", json={"content": content})
    assert submitted.status_code == 201, submitted.text
    receipt = submitted.json()
    result = client.get(f"/api/evaluations/{receipt['evaluation_id']}").json()
    assert result["status"] == "completed"
    assert result["score"] == result["maximum_score"] == 100
    assert len(result["criteria"]) == 3
    assert all(item["passed"] for item in result["criteria"])
    assert result["session_id"] == session_id
    assert result["problem_id"] == "release-plan" and result["problem_version"] == "1.0.0"
    assert result["evidence"][0] == {"kind": "submission", "reference": receipt["submission_id"]}
    detail = client.get(f"/api/sessions/{session_id}").json()
    assert detail["status"] == "submitted"
    assert detail["evaluation_id"] == receipt["evaluation_id"]
    assert len(detail["messages"]) == 2
    trace = client.get(f"/api/sessions/{session_id}/trace").json()
    assert [e["event_type"] for e in trace] == [
        "SESSION_STARTED", "USER_MESSAGE", "ASSISTANT_MESSAGE", "ARTIFACT_UPDATED",
        "SUBMISSION_CREATED", "EVALUATION_COMPLETED", "SESSION_ENDED",
    ]
    assert [e["sequence_number"] for e in trace] == list(range(1, 8))
    assert len({e["event_id"] for e in trace}) == 7
    assert all(e["source"] == "server" and e["session_id"] == session_id and e["schema_version"] == "1.0" for e in trace)
    assert all(datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).tzinfo is not None for e in trace)
    assert trace[0]["payload"]["model_configuration"]["provider"] == "mock"
    assert "manifest_sha256" in trace[0]["payload"]
    assert trace[4]["payload"]["sha256"] == sha256(content.encode()).hexdigest()
    with app.state.session_factory() as db:
        assert len(db.scalars(select(ConversationMessage)).all()) == 2
        submission = db.get(Submission, receipt["submission_id"])
        assert submission.content == content and submission.content_sha256 == sha256(content.encode()).hexdigest()
    # A separate HTTP client with the browser's cookie reloads persisted state.
    with TestClient(app, base_url="http://localhost:8000", cookies={"praxioj_dev_identity": cookie}) as resumed:
        assert resumed.get(f"/api/sessions/{session_id}").json()["evaluation_id"] == receipt["evaluation_id"]
    assert client.post(f"/api/sessions/{session_id}/submissions", json={"content": content}).status_code == 409
    assert client.post(f"/api/sessions/{session_id}/messages", json={"content": "Again"}).status_code == 409


def test_partial_score_and_safe_feedback(client, session):
    response = client.post(f"/api/sessions/{session['id']}/submissions", json={"content": "Goal: release."})
    result = client.get(f"/api/evaluations/{response.json()['evaluation_id']}").json()
    assert result["score"] == 30
    assert [item["passed"] for item in result["criteria"]] == [True, False, False]
    assert "required_terms" not in json.dumps(result)


def test_mock_uses_persisted_conversation_context(client, session):
    path = f"/api/sessions/{session['id']}/messages"
    first = client.post(path, json={"content": "One"}).json()["assistant_message"]["content"]
    second = client.post(path, json={"content": "Two"}).json()["assistant_message"]["content"]
    assert first != second
    assert len(client.get(f"/api/sessions/{session['id']}").json()["messages"]) == 4
    assert [item["sequence_number"] for item in client.get(f"/api/sessions/{session['id']}/trace").json()] == [1, 2, 3, 4, 5]


def test_openapi_has_actual_request_and_response_contracts(client):
    schema = client.get("/api/openapi.json").json()
    assert "/api/sessions/{session_id}/submissions" in schema["paths"]
    assert "ProblemPublic" in schema["components"]["schemas"]
    assert "ContentRequest" in schema["components"]["schemas"]
    assert "required_terms" not in json.dumps(schema)
