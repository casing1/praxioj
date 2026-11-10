"""A legacy Mock response that exceeds Trace storage cannot refund its call."""
from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from conftest import authenticate_client
from praxioj_api.main import create_app
from praxioj_api.models import ConversationMessage, ProviderCall, SolveSession
from praxioj_api.quota_models import ProviderReservation, QuotaBucket


def test_legacy_mock_trace_overflow_preserves_provider_charge_and_consistent_history(app):
    application = create_app(replace(app.state.settings, session_trace_max_events=2))
    with TestClient(application, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as client:
        authenticate_client(client)
        sid = client.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"}).json()["id"]
        # SESSION_STARTED and USER_MESSAGE fit, but the assistant event does not.
        # The savepoint must roll back both messages and USER_MESSAGE only.
        response = client.post(f"/api/sessions/{sid}/messages", json={"content": "hello"})
        assert response.status_code == 429 and response.json()["detail"] == "trace_storage_limit"
        assert response.headers["retry-after"] == "60"
        with application.state.session_factory() as db:
            calls = list(db.scalars(select(ProviderCall).where(ProviderCall.session_id == sid)))
            assert len(calls) == 1 and calls[0].status == "completed"
            assert calls[0].error_code == "trace_storage_limit"
            assert calls[0].estimated
            assert db.get(ProviderReservation, calls[0].id).state == "uncertain"
            assert all(row.model_calls == 1 and row.uncertain_calls == 1 and row.reserved_units > 0
                       for row in db.scalars(select(QuotaBucket)))
            assert db.get(SolveSession, sid).user_message_count == 0
            assert db.scalar(select(func.count()).select_from(ConversationMessage).where(ConversationMessage.session_id == sid)) == 0
            call_id = calls[0].id
        events = client.get(f"/api/sessions/{sid}/trace").json()
        assert [event["event_type"] for event in events] == ["SESSION_STARTED", "ERROR"]
        assert events[-1]["resource_ids"]["call_id"] == call_id
        assert client.get(f"/api/sessions/{sid}/trace/integrity").json()["status"] == "verified"
        assert client.post(f"/api/sessions/{sid}/messages", json={"content": "retry"}).status_code == 429
        assert client.get("/api/account/usage").json()["daily"]["model_calls"] == 1
        assert client.post(f"/api/sessions/{sid}/submissions", json={"content": "Goal verification risk"}).status_code == 201
        assert client.get(f"/api/sessions/{sid}/trace/integrity").json()["status"] == "verified"
