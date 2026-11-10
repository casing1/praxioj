"""Small, role-protected operational views and payload-free request telemetry."""
from datetime import timedelta
import json
import logging
from time import monotonic

from fastapi import HTTPException, Request
from sqlalchemy import func, select

from .auth import aware
from .job_models import Job
from .models import Problem
from .quota_models import QuotaBucket, WorkerRecord
from .quotas import _key, account_usage, bucket_public, day_start
from .security import can_manage_problem, require_role, require_user

logger = logging.getLogger("praxioj.internal.operations")
# Configure only this payload-free channel; enabling global INFO could expose
# HTTP client URLs or database diagnostics through unrelated third-party loggers.
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


class RequestMetricsMiddleware:
    def __init__(self, app, metrics):
        self.app, self.metrics = app, metrics

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        start, status = monotonic(), 500
        async def capture(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
        try:
            await self.app(scope, receive, capture)
        finally:
            elapsed = max(0, (monotonic() - start) * 1000)
            self.metrics["requests"] += 1
            self.metrics["total_duration_ms"] += elapsed
            self.metrics["rate_limit_rejections"] += int(status == 429)
            self.metrics["server_errors"] += int(status >= 500)
            # Fixed categories avoid raw paths, query strings, IDs and unbounded labels.
            path = scope.get("path", "")
            category = next((name for name in ("auth", "sessions", "runs", "admin", "account", "problems")
                if path.startswith("/api/" + name + "/") or path == "/api/" + name), "other")
            method = scope.get("method") if scope.get("method") in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"} else "OTHER"
            logger.info(json.dumps({"event": "api_request", "category": category, "method": method,
                "status": status, "duration_ms": round(elapsed, 3)}, separators=(",", ":")))


class WorkerRegistry:
    def __init__(self, factory, worker_id):
        self.factory, self.worker_id = factory, worker_id

    def touch(self, state, job_id=None, *, recovered=0, finished=False):
        from .jobs import database_now
        with self.factory.begin() as db:
            now = database_now(db)
            row = db.get(WorkerRecord, self.worker_id)
            if row is None:
                row = WorkerRecord(id=self.worker_id, state=state, started_at=now, heartbeat_at=now,
                    completed_jobs=0, failed_jobs=0, recovered_jobs=0, total_wait_seconds=0, total_run_seconds=0)
                db.add(row)
            row.state, row.heartbeat_at, row.current_job_id = state, now, job_id
            row.recovered_jobs += recovered
            if state == "STOPPED":
                row.stopped_at = now
            if finished and job_id:
                job = db.get(Job, job_id)
                if job and job.finished_at is not None:
                    row.completed_jobs += int(job.state == "COMPLETED")
                    row.failed_jobs += int(job.state in {"FAILED", "CANCELLED"})
                    if job.started_at:
                        row.total_wait_seconds += max(0, (aware(job.started_at) - aware(job.available_at)).total_seconds())
                        row.total_run_seconds += max(0, (aware(job.finished_at) - aware(job.started_at)).total_seconds())
                row.current_job_id = None


def operations_snapshot(db, settings, api_metrics):
    from .jobs import database_now
    now = database_now(db)
    counts = dict(db.execute(select(Job.state, func.count()).group_by(Job.state)).all())
    oldest = db.scalar(select(func.min(Job.available_at)).where(Job.state == "PENDING"))
    workers = list(db.scalars(select(WorkerRecord).order_by(WorkerRecord.heartbeat_at.desc()).limit(100)))
    live = [w for w in workers if w.state != "STOPPED" and aware(w.heartbeat_at) > now - timedelta(seconds=settings.worker_lease_seconds * 2)]
    totals = db.execute(select(func.coalesce(func.sum(WorkerRecord.completed_jobs), 0),
        func.coalesce(func.sum(WorkerRecord.failed_jobs), 0), func.coalesce(func.sum(WorkerRecord.recovered_jobs), 0),
        func.coalesce(func.sum(WorkerRecord.total_wait_seconds), 0), func.coalesce(func.sum(WorkerRecord.total_run_seconds), 0),
        func.min(WorkerRecord.started_at), func.count(WorkerRecord.id))).one()
    processed = totals[0] + totals[1]
    first_start = totals[5]
    observation_seconds = max(0, (now - aware(first_start)).total_seconds()) if first_start else 0
    day = day_start(now)
    global_bucket = db.get(QuotaBucket, _key("system", "global", day))
    return {"observed_at": now,
        "queue": {"pending": counts.get("PENDING", 0), "running": counts.get("RUNNING", 0),
            "failed": counts.get("FAILED", 0), "completed": counts.get("COMPLETED", 0),
            "cancelled": counts.get("CANCELLED", 0),
            "oldest_pending_seconds": max(0, (now - aware(oldest)).total_seconds()) if oldest else 0,
            "pending_limit": settings.queue_max_pending, "running_limit": settings.worker_max_running,
            "scheduling": "FIFO among unlocked eligible sessions; account admission caps bound queue monopolization."},
        "workers": [{"id": w.id, "state": w.state if w in live or w.state == "STOPPED" else "STALE",
            "heartbeat_at": w.heartbeat_at, "started_at": w.started_at, "stopped_at": w.stopped_at,
            "current_job_id": w.current_job_id} for w in workers],
        "live_worker_capacity": min(len(live), settings.worker_max_running),
        "worker_list_truncated": totals[6] > 100,
        "processing": {"completed": totals[0], "failed_or_cancelled": totals[1], "lease_recoveries": totals[2],
            "observation_seconds": observation_seconds,
            "throughput_jobs_per_second": processed / observation_seconds if observation_seconds else None,
            "mean_wait_seconds": totals[3] / processed if processed else None,
            "mean_run_seconds": totals[4] / processed if processed else None,
            "failure_ratio": totals[1] / processed if processed else None,
            "scope": "Retained worker records; stopped/stale records expire after 7 days. Abrupt crashes may omit completion counters; queue rows remain authoritative."},
        "daily_system_usage": bucket_public(global_bucket, settings, "system"),
        "api_process": {**api_metrics, "mean_request_ms": api_metrics["total_duration_ms"] / api_metrics["requests"] if api_metrics["requests"] else None,
            "scope": "This API process since startup; structured logs support external aggregation."}}


def install_operations_routes(app):
    app.state.api_metrics = {"requests": 0, "total_duration_ms": 0.0, "rate_limit_rejections": 0, "server_errors": 0}
    app.add_middleware(RequestMetricsMiddleware, metrics=app.state.api_metrics)

    @app.get("/api/account/usage")
    def get_account_usage(request: Request):
        with app.state.session_factory() as db:
            owner = require_user(db, request)
            return account_usage(db, owner, app.state.settings)

    @app.get("/api/admin/operations")
    def get_operations(request: Request):
        with app.state.session_factory() as db:
            require_role(db, request, "administrator")
            return operations_snapshot(db, app.state.settings, app.state.api_metrics)

    @app.get("/api/author/problems/{problem_id}/usage")
    def get_problem_usage(problem_id: str, request: Request):
        from .jobs import database_now
        with app.state.session_factory() as db:
            owner = require_role(db, request, "administrator", "author")
            problem = db.get(Problem, problem_id)
            if not problem or not can_manage_problem(owner, problem):
                raise HTTPException(404, "Resource not found")
            day = day_start(database_now(db))
            bucket = db.get(QuotaBucket, _key("problem", problem.id, day))
            return {"problem_id": problem.id, "window_start": day, "resets_at": day + timedelta(days=1),
                "daily": bucket_public(bucket, app.state.settings, "problem")}
