"""Explicit internal Broker benchmark, excluded from default test_*.py discovery.

Run against a disposable PostgreSQL schema via the normal API fixture:
  .venv/bin/python -m pytest -q -s tests/api/benchmark_judge_lifecycle.py
Set PRAXIOJ_TEST_DATABASE_URL as documented in local-setup.md. No worker thread,
provider call, untrusted execution or application-table cleanup is used. SQL
statements and per-call Broker wall time are not HTTP or runner latency metrics.
"""
import json
import asyncio
from datetime import timedelta
from statistics import median
from time import perf_counter_ns
from sqlalchemy import event, select, text, update
from dataclasses import replace
from uuid import uuid4
from fastapi.testclient import TestClient
from praxioj.execution import FIXTURE_SUBMISSION_CONTENT, MOCK_FIXTURE_ID, MockJudgeBackend
from praxioj_api.judge import JudgeBroker
from praxioj_api.judge_models import JudgeJob
from praxioj_api.jobs import database_now
from praxioj_api.models import User
from conftest import authenticate_client

def benchmark_fixture(app):
    with TestClient(app, base_url="http://localhost:8000", headers={"Origin":"http://localhost:8000"}) as client:
        owner_id = authenticate_client(client)["user"]["id"]
        session = client.post("/api/sessions", json={"problem_id":"release-plan","version":"1.0.0"}).json()
        receipt = client.post(f"/api/sessions/{session['id']}/submissions",json={"content":FIXTURE_SUBMISSION_CONTENT})
        assert receipt.status_code == 201
    broker = JudgeBroker(app.state.session_factory, replace(app.state.settings, judge_backend="mock"))
    with app.state.session_factory.begin() as db:
        owner = db.get(User, owner_id)
        owner.role = "administrator"
        db.flush()
        job = broker.enqueue(db, owner, receipt.json()["submission_id"], str(uuid4()), MOCK_FIXTURE_ID)
    return broker, job


def test_heartbeat_benchmark(app):
    broker, job = benchmark_fixture(app)
    lease = broker.claim("m6-baseline-worker", job_id=job.id)
    for _ in range(20):
        assert broker.heartbeat(lease)
    queries = {"count": 0}
    def count(*_):
        queries["count"] += 1
    event.listen(app.state.engine, "before_cursor_execute", count)
    try:
        samples = []
        counts = []
        for _ in range(7):
            before = queries["count"]
            started = perf_counter_ns()
            for _ in range(100):
                assert broker.heartbeat(lease)
            samples.append((perf_counter_ns() - started) / 100 / 1_000_000)
            counts.append((queries["count"] - before) / 100)
    finally:
        event.remove(app.state.engine, "before_cursor_execute", count)
    print(json.dumps({"target":"Judge heartbeat", "dialect":app.state.engine.dialect.name,
        "warmups":20,"rounds":7,"calls_per_round":100,
        "ms_per_call":samples,"median_ms":median(samples),
        "statements_per_call":counts}))


def test_paired_heartbeat_benchmark(app):
    """Same-version reference keeps the former redundant binding-clock query.

    Both paths run every source/digest/authority check and the fresh final expiry
    check. Alternate order to reduce run drift; report all samples, not a speedup.
    """
    class ExtraBindingClockReference(JudgeBroker):
        def _binding(self, db, owner, session, submission, spec=None, *, now=None):
            return super()._binding(db, owner, session, submission, spec, now=None)

    broker, job = benchmark_fixture(app)
    lease = broker.claim("m6-paired-worker", job_id=job.id)
    paths = {"reference_extra_clock": ExtraBindingClockReference(broker.factory, broker.settings),
        "current_shared_clock": broker}
    for path in paths.values():
        for _ in range(20):
            assert path.heartbeat(lease)
    queries = {"count": 0}
    def count(*_):
        queries["count"] += 1
    metrics = {name: {"ms_per_call": [], "statements_per_call": []} for name in paths}
    event.listen(app.state.engine, "before_cursor_execute", count)
    try:
        for round_number in range(7):
            order = list(paths) if round_number % 2 == 0 else list(reversed(paths))
            for name in order:
                before = queries["count"]
                started = perf_counter_ns()
                for _ in range(100):
                    assert paths[name].heartbeat(lease)
                metrics[name]["ms_per_call"].append((perf_counter_ns() - started) / 100 / 1_000_000)
                metrics[name]["statements_per_call"].append((queries["count"] - before) / 100)
    finally:
        event.remove(app.state.engine, "before_cursor_execute", count)
    for values in metrics.values():
        values["median_ms"] = median(values["ms_per_call"])
        values["range_ms"] = [min(values["ms_per_call"]), max(values["ms_per_call"])]
    print(json.dumps({"target": "Paired same-process Judge heartbeat", "dialect": app.state.engine.dialect.name,
        "warmups_per_path": 20, "rounds": 7, "calls_per_round_per_path": 100,
        "order": "alternating", "paths": metrics}))


def test_cleanup_batch_benchmark(app):
    """Observational new-path cost; M5 had no purge to claim a speedup against."""
    original, first = benchmark_fixture(app)
    broker = JudgeBroker(original.factory, replace(original.settings, judge_account_retained_jobs=256))
    ids = []
    for number in range(100):
        if number == 0:
            job = first
        else:
            with broker.factory.begin() as db:
                job = broker.enqueue(db, db.get(User, first.owner_id), first.submission_id, str(uuid4()), MOCK_FIXTURE_ID)
        lease = broker.claim("m6-cleanup-benchmark", job.id)
        broker.complete(lease, asyncio.run(MockJudgeBackend().execute(lease.request)))
        ids.append(job.id)
    with broker.factory.begin() as db:
        db.execute(update(JudgeJob).where(JudgeJob.id.in_(ids))
            .values(finished_at=database_now(db) - timedelta(days=8)))
        active = broker.enqueue(db, db.get(User, first.owner_id), first.submission_id, str(uuid4()), MOCK_FIXTURE_ID)
    plan_summary = None
    if app.state.engine.dialect.name == "postgresql":
        with broker.factory() as db:
            now = database_now(db)
            plan = db.execute(text("""EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT id FROM judge_jobs WHERE state IN ('COMPLETED','FAILED','CANCELLED')
                AND finished_at <= :payload AND (evidence_purged_at IS NULL OR finished_at <= :metadata)
                ORDER BY finished_at,id LIMIT 100"""), {"payload": now - timedelta(days=7),
                    "metadata": now - timedelta(days=30)}).scalar_one()[0]
            nodes = []
            def visit(node):
                nodes.append(node["Node Type"])
                for child in node.get("Plans", []):
                    visit(child)
            visit(plan["Plan"])
            plan_summary = {"node_types": nodes, "actual_rows": plan["Plan"]["Actual Rows"],
                "planning_ms": plan["Planning Time"], "execution_ms": plan["Execution Time"]}
    metrics = {}
    queries = {"count": 0}
    def count(*_):
        queries["count"] += 1
    for phase in ("payload", "metadata"):
        if phase == "metadata":
            with broker.factory.begin() as db:
                db.execute(update(JudgeJob).where(JudgeJob.id.in_(ids))
                    .values(finished_at=database_now(db) - timedelta(days=31)))
        queries["count"] = 0
        event.listen(app.state.engine, "before_cursor_execute", count)
        try:
            started = perf_counter_ns()
            result = broker.purge_history(limit=100)
            elapsed = (perf_counter_ns() - started) / 1_000_000
        finally:
            event.remove(app.state.engine, "before_cursor_execute", count)
        assert result["purged_judge_payloads" if phase == "payload" else "deleted_judge_jobs"] == 100
        metrics[phase] = {"elapsed_ms": elapsed, "sql_statements": queries["count"], "counts": result}
    with broker.factory() as db:
        assert db.get(JudgeJob, active.id).state == "PENDING"
        assert list(db.scalars(select(JudgeJob.id))) == [active.id]
    assert not any(broker.purge_history().values())
    print(json.dumps({"target": "Bounded Judge cleanup", "dialect": app.state.engine.dialect.name,
        "terminal_jobs": 100, "owners": 1, "live_jobs_preserved": 1,
        "baseline": "M5 has no terminal purge; no before/after speedup claimed",
        "selector_plan": plan_summary, "phases": metrics}))
