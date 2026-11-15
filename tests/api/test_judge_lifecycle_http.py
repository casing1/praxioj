"""Owned HTTP projections/export/deletion after Judge evidence retention."""
import json
from sqlalchemy import func, select

from praxioj_api.judge_models import JudgeAttempt, JudgeJob
from test_judge_lifecycle import age_job
from test_judge_routes import actor, confirm, enqueue, judge_app, synthetic_submission


def test_retained_assessment_exposes_unavailable_evidence_in_get_export_and_erasure(judge_app):
    with actor(judge_app) as client:
        sid, receipt = synthetic_submission(client)
        original = client.get(f"/api/evaluations/{receipt['evaluation_id']}").json()
        job_id = enqueue(client, receipt)[0].json()["id"]
        assert client.post(f"/api/internal/judge/jobs/{job_id}/dispatch", json={}).status_code == 200
        age_job(judge_app, job_id, 8)
        assert judge_app.state.judge_broker.purge_history()["purged_judge_payloads"] == 1
        public = client.get(f"/api/internal/judge/jobs/{job_id}").json()
        assert public["evidence_status"] == "unavailable" and public["result"] is None
        assert public["assessment"]["evidence_status"] == "unavailable"
        assert public["assessment"]["evaluation"]["score"] == 100
        assert client.get(f"/api/evaluations/{receipt['evaluation_id']}").json() == original
        assert client.get(f"/api/sessions/{sid}/trace/integrity").json()["status"] == "verified"
        confirm(client)
        exported = client.post("/api/auth/export", json={}).json()
        history = exported["judge_executions"][0]
        assert history["evidence_status"] == "unavailable" and history["trace_availability"] == "available"
        serialized = json.dumps(exported)
        for private in ("capability_hash", "worker_id", "request_template"):
            assert private not in serialized
        assert client.post("/api/auth/delete", json={}).status_code == 200
    with judge_app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(JudgeJob)) == 0
        assert db.scalar(select(func.count()).select_from(JudgeAttempt)) == 0
