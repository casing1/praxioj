"""Real authentication and data lifecycle around the opt-in synthetic HTTP broker."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from praxioj.execution import MOCK_FIXTURE_ID, MOCK_SUBMISSION_CONTENT, MockJudgeBackend
from praxioj_api.main import create_app
from praxioj_api.judge_models import JudgeAttempt, JudgeJob
from praxioj_api.models import Evaluation, SolveSession, User, utcnow
from praxioj_api.retention import purge_expired
from conftest import authenticate_client


@pytest.fixture
def judge_app(app):
    configured = create_app(replace(app.state.settings, judge_backend="mock"))
    yield configured
    configured.state.engine.dispose()


@contextmanager
def actor(app, role="administrator"):
    with TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as client:
        auth = authenticate_client(client)
        with app.state.session_factory.begin() as db:
            db.get(User, auth["user"]["id"]).role = role
        yield client


def synthetic_submission(client, content=MOCK_SUBMISSION_CONTENT):
    session = client.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"})
    assert session.status_code == 201
    receipt = client.post(f"/api/sessions/{session.json()['id']}/submissions", json={"content": content})
    assert receipt.status_code == 201, receipt.text
    return session.json()["id"], receipt.json()


def enqueue(client, receipt, **updates):
    body = {"submission_id": receipt["submission_id"], "request_id": str(uuid4()), "fixture_id": MOCK_FIXTURE_ID, **updates}
    return client.post("/api/internal/judge/jobs", json=body), body


def confirm(client):
    assert client.post("/api/auth/reauthenticate", json={"password": "synthetic-test-passphrase-2026"}).status_code == 200


def test_default_backend_rejects_dispatch_without_invoking_mock(app, monkeypatch):
    async def forbidden(*_):
        raise AssertionError("Unavailable mode dispatched a backend")
    monkeypatch.setattr(MockJudgeBackend, "execute", forbidden)
    with actor(app) as client:
        runtime = client.get("/api/internal/judge/runtime").json()
        assert runtime["availability"]["status"] == "unavailable"
        assert runtime["independent_execution_evidence"] is False
        _, receipt = synthetic_submission(client)
        response, _ = enqueue(client, receipt)
        assert response.status_code == 503
        assert response.json() == {"detail": "runtime_unavailable"}
        with app.state.session_factory() as db:
            assert db.scalar(select(func.count()).select_from(JudgeJob)) == 0


def test_synthetic_routes_require_auth_role_csrf_and_bounded_intent(judge_app):
    with TestClient(judge_app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as anonymous:
        assert anonymous.post("/api/internal/judge/jobs", json={"submission_id": str(uuid4()), "request_id": str(uuid4()), "fixture_id": MOCK_FIXTURE_ID}).status_code == 401
    with actor(judge_app, "participant") as participant:
        assert participant.get("/api/internal/judge/runtime").status_code == 403
        _, receipt = synthetic_submission(participant)
        assert enqueue(participant, receipt)[0].status_code == 403
    with actor(judge_app) as client:
        _, receipt = synthetic_submission(client)
        response, body = enqueue(client, receipt, command="do not execute")
        assert response.status_code == 422 and "do not execute" not in response.text
        body.pop("command")
        csrf = client.headers.pop("X-CSRF-Token")
        assert client.post("/api/internal/judge/jobs", json=body).status_code == 403
        client.headers["X-CSRF-Token"] = csrf
        assert client.post("/api/internal/judge/jobs", json=body, headers={"Origin": "https://hostile.example"}).status_code == 403
        assert enqueue(client, receipt, fixture_id="unrecognized-fixture")[0].status_code == 422
        _, other_text = synthetic_submission(client, "A participant's text is never a synthetic execution fixture.")
        assert enqueue(client, other_text)[0].status_code == 422


def test_admin_cannot_bind_read_dispatch_or_cancel_another_accounts_job(judge_app):
    with actor(judge_app) as first, actor(judge_app) as second:
        _, receipt = synthetic_submission(first)
        response, _ = enqueue(first, receipt)
        assert response.status_code == 202
        job_id = response.json()["id"]
        assert enqueue(second, receipt)[0].status_code == 404
        assert second.get(f"/api/internal/judge/jobs/{job_id}").status_code == 404
        for operation in ("cancel", "dispatch"):
            assert second.post(f"/api/internal/judge/jobs/{job_id}/{operation}", json={}).status_code == 404


def test_http_execution_is_synthetic_separate_from_original_score_and_exported_safely(judge_app):
    with actor(judge_app) as client:
        sid, receipt = synthetic_submission(client)
        original = client.get(f"/api/evaluations/{receipt['evaluation_id']}").json()
        before = client.get(f"/api/sessions/{sid}/trace/integrity").json()
        response, body = enqueue(client, receipt)
        assert response.status_code == 202
        job_id = response.json()["id"]
        assert client.post("/api/internal/judge/jobs", json=body).json()["id"] == job_id
        completed = client.post(f"/api/internal/judge/jobs/{job_id}/dispatch", json={})
        assert completed.status_code == 200, completed.text
        job = completed.json()
        assert job["state"] == "COMPLETED" and job["provenance"] == "synthetic_mock"
        assert job["assessment"]["independent_execution_evidence"] is False
        assert job["assessment"]["evaluation"]["score"] == 100
        assert client.post(f"/api/internal/judge/jobs/{job_id}/dispatch", json={}).status_code == 409
        assert client.get(f"/api/evaluations/{receipt['evaluation_id']}").json() == original
        after = client.get(f"/api/sessions/{sid}/trace/integrity").json()
        assert before == after and after["status"] == "verified"
        confirm(client)
        exported = client.post("/api/auth/export", json={}).json()
        assert [item["id"] for item in exported["judge_executions"]] == [job_id]
        serialized = json.dumps(exported)
        for private_field in ("capability_hash", "worker_id", "request_template", "spec_digest"):
            assert private_field not in serialized
        with judge_app.state.session_factory() as db:
            attempt = db.scalar(select(JudgeAttempt))
            assert attempt.consumed_at is not None and attempt.capability_hash not in serialized
            assert db.scalar(select(func.count()).select_from(Evaluation)) == 1


def test_active_judge_blocks_erasure_then_cancelled_job_cascades(judge_app):
    with actor(judge_app) as client:
        _, receipt = synthetic_submission(client)
        response, _ = enqueue(client, receipt)
        job_id = response.json()["id"]
        lease = judge_app.state.judge_broker.claim("synthetic-test-worker", job_id=job_id)
        confirm(client)
        assert client.post("/api/auth/delete", json={}).status_code == 409
        assert client.post(f"/api/internal/judge/jobs/{job_id}/cancel", json={}).status_code == 200
        assert judge_app.state.judge_broker.heartbeat(lease) is False
        assert client.post("/api/auth/delete", json={}).status_code == 200
        with judge_app.state.session_factory() as db:
            assert db.scalar(select(func.count()).select_from(JudgeJob)) == 0
            assert db.scalar(select(func.count()).select_from(JudgeAttempt)) == 0


def test_trace_purge_closes_judge_and_releases_reservation_without_trace_append(judge_app):
    with actor(judge_app) as client:
        sid, receipt = synthetic_submission(client)
        response, _ = enqueue(client, receipt)
        job_id = response.json()["id"]
        with judge_app.state.session_factory.begin() as db:
            session = db.get(SolveSession, sid)
            checkpoint = session.trace_head_sha256
            session.trace_expires_at = utcnow() - timedelta(seconds=1)
        assert purge_expired(judge_app.state.session_factory, judge_app.state.settings) == 1
        with judge_app.state.session_factory() as db:
            job = db.get(JudgeJob, job_id)
            assert job.state == "FAILED" and job.error_code == "trace_expired"
            assert job.reservation_active is False
            assert db.get(SolveSession, sid).trace_head_sha256 == checkpoint
        assert client.post(f"/api/internal/judge/jobs/{job_id}/dispatch", json={}).status_code == 409
        confirm(client)
        exported = client.post("/api/auth/export", json={}).json()
        assert exported["traces"] == []
        assert exported["judge_executions"][0]["trace_availability"] == "expired"


@pytest.mark.parametrize("malformed", [False, True])
def test_dispatch_faults_have_safe_codes_and_release_capacity(judge_app, malformed):
    class FaultingBackend:
        async def execute(self, request):
            raise RuntimeError("private synthetic backend diagnostic")
    with actor(judge_app) as client:
        _, receipt = synthetic_submission(client)
        job_id = enqueue(client, receipt)[0].json()["id"]
        judge_app.state.judge_execution_backend = MockJudgeBackend("malformed") if malformed else FaultingBackend()
        response = client.post(f"/api/internal/judge/jobs/{job_id}/dispatch", json={})
        assert response.status_code == (200 if malformed else 409)
        assert "private synthetic backend diagnostic" not in response.text
        public = client.get(f"/api/internal/judge/jobs/{job_id}").json()
        assert public["state"] == "FAILED" and public["assessment"] is None
        assert public["error_code"] == ("invalid_result" if malformed else "backend_error")
        with judge_app.state.session_factory() as db:
            assert db.get(JudgeJob, job_id).reservation_active is False


def test_quarantined_database_blocks_every_judge_authority_entrypoint(judge_app):
    import asyncio
    from sqlalchemy import text
    with actor(judge_app) as client:
        _, receipt = synthetic_submission(client)
        job_id = enqueue(client, receipt)[0].json()["id"]
        broker = judge_app.state.judge_broker
        lease = broker.claim("synthetic-quarantine-probe", job_id=job_id)
        raw = asyncio.run(MockJudgeBackend().execute(lease.request))
        with judge_app.state.session_factory.begin() as db:
            db.execute(text("CREATE TABLE praxioj_restore_quarantine (id INTEGER)"))
        for operation in (lambda: broker.claim("synthetic-quarantine-probe"),
                lambda: broker.heartbeat(lease), lambda: broker.complete(lease, raw),
                lambda: broker.fail(lease), lambda: broker.recover()):
            with pytest.raises(RuntimeError, match="quarantined"):
                operation()
        with judge_app.state.session_factory.begin() as db:
            owner = db.get(User, db.get(JudgeJob, job_id).owner_id)
            with pytest.raises(RuntimeError, match="quarantined"):
                broker.enqueue(db, owner, receipt["submission_id"], str(uuid4()), MOCK_FIXTURE_ID)
            with pytest.raises(RuntimeError, match="quarantined"):
                broker.cancel(db, owner, job_id)
            job = db.get(JudgeJob, job_id)
            assert job.state == "RUNNING" and job.reservation_active is True
            assert db.get(JudgeAttempt, lease.attempt_id).consumed_at is None
