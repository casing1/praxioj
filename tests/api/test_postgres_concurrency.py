"""Real row-lock verification, intentionally skipped by the SQLite fast suite."""
from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
from fastapi.testclient import TestClient
import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("PRAXIOJ_TEST_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")),
    reason="PostgreSQL URL required for real row-lock concurrency verification",
)


def test_concurrent_messages_receive_contiguous_sequences(client, app, session):
    gate = Barrier(2)
    cookie = client.cookies["praxioj_session"]
    def send(content):
        with TestClient(app, base_url="http://localhost:8000", cookies={"praxioj_session": cookie}, headers={"X-CSRF-Token": client.headers["X-CSRF-Token"], "Origin": "http://localhost:8000"}) as worker:
            gate.wait(timeout=10)
            return worker.post(f"/api/sessions/{session['id']}/messages", json={"content": content})
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(send, ["First concurrent message", "Second concurrent message"]))
    assert [result.status_code for result in results] == [200, 200]
    events = client.get(f"/api/sessions/{session['id']}/trace").json()
    assert [event["sequence_number"] for event in events] == [1, 2, 3, 4, 5]
    assert [event["event_type"] for event in events] == ["SESSION_STARTED", "USER_MESSAGE", "ASSISTANT_MESSAGE", "USER_MESSAGE", "ASSISTANT_MESSAGE"]
    assert len(client.get(f"/api/sessions/{session['id']}").json()["messages"]) == 4


def test_concurrent_final_submissions_create_one_evaluation(client, app, session):
    gate = Barrier(2)
    cookie = client.cookies["praxioj_session"]
    def submit(_):
        with TestClient(app, base_url="http://localhost:8000", cookies={"praxioj_session": cookie}, headers={"X-CSRF-Token": client.headers["X-CSRF-Token"], "Origin": "http://localhost:8000"}) as worker:
            gate.wait(timeout=10)
            return worker.post(f"/api/sessions/{session['id']}/submissions", json={"content": "Goal Verification Risk"})
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, [1, 2]))
    assert sorted(result.status_code for result in results) == [201, 409]
    events = client.get(f"/api/sessions/{session['id']}/trace").json()
    assert sum(event["event_type"] == "SUBMISSION_CREATED" for event in events) == 1
    assert sum(event["event_type"] == "EVALUATION_COMPLETED" for event in events) == 1
    assert [event["sequence_number"] for event in events] == list(range(1, 6))
