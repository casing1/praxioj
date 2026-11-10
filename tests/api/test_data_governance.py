"""Owner export, recent confirmation, transactional deletion and bounded queries."""
from dataclasses import replace
from datetime import timedelta
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, func, select

from praxioj_api.models import (AuthSession, ConversationMessage, Evaluation, SolveSession,
                               Submission, TraceEvent, User, utcnow)
from praxioj_api.quota_models import QuotaBucket
from praxioj_api.retention import erase_account
from praxioj_api.retention_models import AuditRecord
from conftest import authenticate_client


def confirm(client):
    result = client.post("/api/auth/reauthenticate", json={"password": "synthetic-test-passphrase-2026"})
    assert result.status_code == 200, result.text


def test_export_requires_fresh_confirmation_and_never_exports_other_accounts(client, session, app):
    sid = session["id"]
    client.post(f"/api/sessions/{sid}/messages", json={"content": "owner export canary"})
    receipt = client.post(f"/api/sessions/{sid}/submissions", json={"content": "Goal verification risk"}).json()
    with TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as other:
        authenticate_client(other)
        outsider = other.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"}).json()["id"]
        other.put(f"/api/sessions/{outsider}/draft", json={"content": "foreign export canary"})
    assert client.post("/api/auth/export", json={}).status_code == 403
    confirm(client)
    response = client.post("/api/auth/export", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "praxioj-account-export/1"
    assert [row["id"] for row in payload["sessions"]] == [sid]
    assert payload["evaluations"][0]["id"] == receipt["evaluation_id"]
    assert payload["messages"] and payload["traces"] and payload["submissions"] and payload["provider_usage"]
    assert payload["next_cursor"] is None
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    assert "owner export canary" in response.text and "foreign export canary" not in response.text
    for forbidden in ("password_hash", "identity_token_hash", "token_hash", "csrf_hash", "claim_token", "profile_snapshot"):
        assert forbidden not in response.text
    with app.state.session_factory.begin() as db:
        auth = db.scalar(select(AuthSession).where(AuthSession.user_id == payload["profile"]["id"], AuthSession.revoked_at.is_(None)))
        auth.reauthenticated_at = utcnow() - timedelta(minutes=10)
    assert client.post("/api/auth/export", json={}).status_code == 403


def test_export_paginates_without_duplicates_and_omits_expired_evidence(client, session, app):
    ids = [session["id"]]
    ids.append(client.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"}).json()["id"])
    receipt = client.post(f"/api/sessions/{ids[0]}/submissions", json={"content": "Goal verification risk"}).json()
    with app.state.session_factory.begin() as db:
        db.get(SolveSession, ids[0]).trace_expires_at = utcnow() - timedelta(seconds=1)
    confirm(client)
    page1 = client.post("/api/auth/export", json={"limit": 1}).json()
    page2 = client.post("/api/auth/export", json={"limit": 1, "after_session_id": page1["next_cursor"]}).json()
    assert page1["next_cursor"] is not None and page2["next_cursor"] is None
    assert sorted([page1["sessions"][0]["id"], page2["sessions"][0]["id"]]) == sorted(ids)
    expired_page = page1 if page1["sessions"][0]["id"] == ids[0] else page2
    assert expired_page["sessions"][0]["trace_availability"] == "expired"
    assert expired_page["traces"] == []
    assert expired_page["evaluations"][0]["id"] == receipt["evaluation_id"]
    assert expired_page["evaluations"][0]["trace_availability"] == "expired"


def test_export_has_size_limits_and_csrf_protection(client, session, app):
    client.put(f"/api/sessions/{session['id']}/draft", json={"content": "x" * 5000})
    confirm(client)
    app.state.settings = replace(app.state.settings, export_max_bytes=1024)
    assert client.post("/api/auth/export", json={}).status_code == 413
    assert client.post("/api/auth/export", json={"limit": 101}).status_code == 422
    assert client.post("/api/auth/export", json={}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.action == "account_exported")) == 0


def test_export_row_limit_never_returns_a_partial_session(client, session, app):
    with app.state.session_factory.begin() as db:
        db.add_all(ConversationMessage(session_id=session["id"], position=position, role="user", content="synthetic")
                   for position in range(1, 102))
    confirm(client)
    app.state.settings = replace(app.state.settings, export_max_rows=100)
    response = client.post("/api/auth/export", json={"limit": 1})
    assert response.status_code == 413
    assert "sessions" not in response.json()
    assert client.post("/api/auth/export", json={"user_id": str(uuid4())}).status_code == 422


def test_deletion_requires_confirmation_rolls_back_and_can_retry(client, session, app, monkeypatch):
    sid = session["id"]
    user_id = client.get("/api/auth/me").json()["user"]["id"]
    client.post(f"/api/sessions/{sid}/messages", json={"content": "survives rollback"})
    assert client.post("/api/auth/delete", json={}).status_code == 403
    from praxioj_api import retention
    original = retention.audit
    with pytest.raises(RuntimeError):
        with app.state.session_factory.begin() as db:
            user = db.scalar(select(User).where(User.id == user_id).with_for_update())
            monkeypatch.setattr(retention, "audit", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("synthetic rollback")))
            erase_account(db, user)
    monkeypatch.setattr(retention, "audit", original)
    assert client.get(f"/api/sessions/{sid}").status_code == 200
    confirm(client)
    assert client.post("/api/auth/delete", json={}).json() == {"deleted_sessions": 1}
    assert client.post("/api/auth/delete", json={}).status_code == 401
    with app.state.session_factory.begin() as db:
        assert erase_account(db, db.get(User, user_id)) == {"deleted_sessions": 0}
        assert db.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.action == "account_erased")) == 1
        for model in (SolveSession, ConversationMessage, TraceEvent, Submission, Evaluation, AuthSession):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_deletion_query_count_is_independent_of_owned_session_count(app):
    """No per-session child DELETE loop; this guards the measured N+1 removal."""
    counts = []
    for amount in (1, 10):
        with app.state.session_factory.begin() as db:
            user = User(identity_token_hash=uuid4().hex, username=uuid4().hex, is_active=True)
            db.add(user); db.flush(); owner_id = user.id
            from praxioj_api.models import ProblemVersion
            version = db.scalar(select(ProblemVersion))
            for _ in range(amount):
                db.add(SolveSession(user_id=owner_id, problem_version_id=version.id, model_configuration={}))
        queries = []
        def record(_conn, _cursor, statement, _parameters, _context, _many):
            queries.append(statement)
        event.listen(app.state.engine, "before_cursor_execute", record)
        try:
            with app.state.session_factory.begin() as db:
                erase_account(db, db.get(User, owner_id))
        finally:
            event.remove(app.state.engine, "before_cursor_execute", record)
        counts.append(len(queries))
    assert counts[0] == counts[1]


def test_export_user_quota_is_private_and_erased(client, app):
    owner = client.get("/api/auth/me").json()["user"]["id"]
    with app.state.session_factory.begin() as db:
        db.add(QuotaBucket(key="a" * 64, scope="user", subject=owner, window_start=utcnow(), model_calls=2))
        db.add(QuotaBucket(key="b" * 64, scope="user", subject=str(uuid4()), window_start=utcnow(), model_calls=999))
    confirm(client)
    payload = client.post("/api/auth/export", json={}).json()
    assert [row["model_calls"] for row in payload["account_usage"]] == [2]
    assert "999" not in json.dumps(payload)
    assert client.post("/api/auth/delete", json={}).status_code == 200
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(QuotaBucket).where(QuotaBucket.subject == owner)) == 0
