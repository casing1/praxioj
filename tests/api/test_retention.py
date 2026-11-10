"""Persisted integrity, bounded deletion, and reviewer access integration checks."""
from datetime import timedelta
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from praxioj_api.models import (AuthSession, ConversationMessage, Evaluation, Problem, SolveSession,
                               Submission, TraceEvent, User, WorkspaceFile, utcnow)
from praxioj_api.retention import purge_expired
from praxioj_api.retention_models import AuditRecord
from praxioj_api.quota_models import TraceUsage
from conftest import authenticate_client


def reviewer(app, role="author", owns=True):
    browser = TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"})
    identity = authenticate_client(browser)
    with app.state.session_factory.begin() as db:
        user = db.get(User, identity["user"]["id"])
        user.role = role
        if owns:
            db.get(Problem, "release-plan").author_id = user.id
    return browser


def test_persisted_chain_detects_payload_tamper_and_missing_tail(client, session, app):
    sid = session["id"]
    assert client.post(f"/api/sessions/{sid}/messages", json={"content": "Synthetic private message"}).status_code == 200
    url = f"/api/sessions/{sid}/trace/integrity"
    assert client.get(url).json()["status"] == "verified"
    with app.state.session_factory.begin() as db:
        event = db.scalar(select(TraceEvent).where(TraceEvent.session_id == sid).order_by(TraceEvent.sequence_number.desc()))
        original = event.envelope
        event.envelope = {**original, "payload": {"content": "changed"}}
    assert client.get(url).json()["status"] == "invalid"
    with app.state.session_factory.begin() as db:
        event = db.get(TraceEvent, original["event_id"])
        event.envelope = original
    assert client.get(url).json()["status"] == "verified"
    with app.state.session_factory.begin() as db:
        db.delete(db.get(TraceEvent, original["event_id"]))
    assert client.get(url).json()["status"] == "invalid"


def test_expired_trace_is_purged_but_evaluation_marks_evidence_unavailable(client, session, app):
    sid = session["id"]
    receipt = client.post(f"/api/sessions/{sid}/submissions", json={"content": "Goal verification risk"}).json()
    with app.state.session_factory.begin() as db:
        row = db.get(SolveSession, sid)
        row.trace_expires_at = utcnow() - timedelta(seconds=1)
        head = row.trace_head_sha256
    assert client.get(f"/api/sessions/{sid}/trace").status_code == 410
    assert purge_expired(app.state.session_factory, app.state.settings) == 1
    assert purge_expired(app.state.session_factory, app.state.settings) == 0
    with app.state.session_factory() as db:
        usage = db.get(TraceUsage, sid)
        assert usage is None or usage.bytes_used == 0
        assert db.scalar(select(func.count()).select_from(TraceEvent).where(TraceEvent.session_id == sid)) == 0
        record = db.scalar(select(AuditRecord).where(AuditRecord.action == "trace_expired"))
        assert record.details["head_sha256"] == head and record.details["deleted_events"] > 0
        assert "Goal verification risk" not in json.dumps(record.details)
    assert client.get(f"/api/evaluations/{receipt['evaluation_id']}").json()["trace_availability"] == "expired"
    assert client.get(f"/api/sessions/{sid}/trace/integrity").json()["status"] == "expired"


def test_idle_expiry_blocks_new_work_and_retention_does_not_delete_active_run(client, session, app):
    sid = session["id"]
    with app.state.session_factory.begin() as db:
        row = db.get(SolveSession, sid)
        row.trace_expires_at = utcnow() - timedelta(seconds=1)
        row.active_run_id = str(uuid4())
    assert purge_expired(app.state.session_factory, app.state.settings) == 0
    assert client.post(f"/api/sessions/{sid}/runs", json={"request_id": str(uuid4()), "content": "test"}).status_code == 410
    assert client.put(f"/api/sessions/{sid}/draft", json={"content": "expired write"}).status_code == 410
    assert client.post("/api/auth/reauthenticate", json={"password": "synthetic-test-passphrase-2026"}).status_code == 200
    assert client.post("/api/auth/delete", json={}).status_code == 409
    with app.state.session_factory.begin() as db:
        db.get(SolveSession, sid).active_run_id = None
    assert purge_expired(app.state.session_factory, app.state.settings) == 1
    assert client.get(f"/api/sessions/{sid}").json()["status"] == "ended"


def test_author_review_is_problem_scoped_and_excludes_conversation_payloads(client, session, app):
    sid = session["id"]
    client.post(f"/api/sessions/{sid}/messages", json={"content": "Synthetic participant-only text"})
    receipt = client.post(f"/api/sessions/{sid}/submissions", json={"content": "Goal verification risk"}).json()
    path = f"/api/review/sessions/{sid}/trace"
    assert client.get(path).status_code == 403
    with reviewer(app) as author, reviewer(app, owns=False) as stranger:
        assert stranger.get(path).status_code == 404
        result = author.get(path)
        assert result.status_code == 200
        assert result.json()["integrity"]["status"] == "verified"
        assert "Synthetic participant-only text" not in result.text
        assert "event_hash" not in json.dumps(result.json()["events"])
        assert author.get(f"/api/sessions/{sid}/trace").status_code == 404
        assert author.get(f"/api/evaluations/{receipt['evaluation_id']}").status_code == 404
        evaluations = author.get("/api/review/problems/release-plan/evaluations")
        assert evaluations.status_code == 200 and len(evaluations.json()) == 1
        assert stranger.get("/api/review/problems/release-plan/evaluations").status_code == 404
        assert author.get("/api/admin/audit").status_code == 403
    with reviewer(app, role="administrator", owns=False) as admin:
        records = admin.get("/api/admin/audit")
        assert records.status_code == 200
        assert any(record["action"] == "trace_reviewed" for record in records.json())
        assert "Synthetic participant-only text" not in records.text


def test_account_erasure_removes_private_content_and_revokes_other_logins(client, session, app):
    sid = session["id"]
    user_id = client.get("/api/auth/me").json()["user"]["id"]
    client.post(f"/api/sessions/{sid}/messages", json={"content": "private canary"})
    receipt = client.post(f"/api/sessions/{sid}/submissions", json={"content": "private final canary"}).json()
    assert client.post("/api/auth/reauthenticate", json={"password": "synthetic-test-passphrase-2026"}).status_code == 200
    assert client.post("/api/auth/delete", json={}).json() == {"deleted_sessions": 1}
    assert client.get("/api/auth/me").status_code == 401
    assert client.get(f"/api/evaluations/{receipt['evaluation_id']}").status_code == 401
    with app.state.session_factory() as db:
        user = db.get(User, user_id)
        assert not user.is_active and user.username is None and user.password_hash is None
        assert db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.user_id == user_id)) == 0
        for model in (SolveSession, ConversationMessage, TraceEvent, Submission, Evaluation, WorkspaceFile):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        audit = db.scalar(select(AuditRecord).where(AuditRecord.action == "account_erased"))
        assert audit.details["deleted_sessions"] == 1
        assert "private" not in json.dumps(audit.details)


def test_audit_records_have_bounded_retention(app):
    with app.state.session_factory.begin() as db:
        db.add(AuditRecord(action="old_synthetic", details={}, created_at=utcnow() - timedelta(days=91)))
    purge_expired(app.state.session_factory, app.state.settings)
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditRecord)) == 0
