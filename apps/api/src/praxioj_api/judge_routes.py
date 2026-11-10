"""Administrator-owned synthetic Judge harness; never accepts code or runtime policy."""
import asyncio
from uuid import UUID, uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import Field

from praxioj.core import DomainModel
from praxioj.execution import MOCK_FIXTURE_ID, MOCK_SUBMISSION_CONTENT, MockJudgeBackend, UnavailableExecutionBackend
from .judge import JudgeBroker, JudgeError, judge_public
from .security import require_role


class SyntheticJudgeCreate(DomainModel):
    request_id: UUID
    submission_id: UUID
    fixture_id: str = Field(min_length=1, max_length=64)


class EmptyJudgeMutation(DomainModel):
    pass


async def dispatch_mock(broker, backend, job_id):
    """Trusted one-shot mock delivery. Neither app settings nor tokens reach backend."""
    lease = await asyncio.to_thread(broker.claim, "synthetic-" + uuid4().hex, job_id=job_id)
    if lease is None:
        raise JudgeError("judge_not_claimable", 409)
    try:
        raw = await asyncio.wait_for(backend.execute(lease.request), timeout=30)
    except asyncio.CancelledError:
        await asyncio.to_thread(broker.fail, lease, "backend_error")
        raise
    except TimeoutError:
        await asyncio.to_thread(broker.fail, lease, "backend_error")
        raise JudgeError("backend_error", 409) from None
    except Exception:
        await asyncio.to_thread(broker.fail, lease, "backend_error")
        raise JudgeError("backend_error", 409) from None
    return await asyncio.to_thread(broker.complete, lease, raw)


def install_judge_routes(app):
    broker = JudgeBroker(app.state.session_factory, app.state.settings)
    app.state.judge_broker = broker
    app.state.judge_execution_backend = (MockJudgeBackend() if app.state.settings.judge_backend == "mock"
        else UnavailableExecutionBackend())

    @app.exception_handler(JudgeError)
    async def judge_error(_request, error):
        return JSONResponse({"detail": error.code}, status_code=error.status)

    @app.get("/api/internal/judge/runtime", tags=["Synthetic Judge testing"])
    def synthetic_runtime(request: Request):
        with app.state.session_factory() as db:
            require_role(db, request, "administrator")
        backend = app.state.judge_execution_backend
        return {"availability": backend.availability().model_dump(mode="json"),
            "capabilities": backend.capabilities.model_dump(mode="json"),
            "independent_execution_evidence": False,
            "fixture": {"id": MOCK_FIXTURE_ID, "submission_content": MOCK_SUBMISSION_CONTENT,
                "problem_id": "release-plan", "version": "1.0.0"}}

    @app.post("/api/internal/judge/jobs", status_code=202, tags=["Synthetic Judge testing"])
    def create_synthetic_job(body: SyntheticJudgeCreate, request: Request):
        with app.state.session_factory.begin() as db:
            owner = require_role(db, request, "administrator")
            job = broker.enqueue(db, owner, str(body.submission_id), str(body.request_id), body.fixture_id)
            return judge_public(job)

    @app.get("/api/internal/judge/jobs/{job_id}", tags=["Synthetic Judge testing"])
    def get_synthetic_job(job_id: UUID, request: Request):
        with app.state.session_factory() as db:
            owner = require_role(db, request, "administrator")
            return judge_public(broker.get_owned(db, owner, str(job_id)))

    @app.post("/api/internal/judge/jobs/{job_id}/cancel", tags=["Synthetic Judge testing"])
    def cancel_synthetic_job(job_id: UUID, body: EmptyJudgeMutation, request: Request):
        with app.state.session_factory.begin() as db:
            owner = require_role(db, request, "administrator")
            return judge_public(broker.cancel(db, owner, str(job_id)))

    @app.post("/api/internal/judge/jobs/{job_id}/dispatch", tags=["Synthetic Judge testing"])
    async def dispatch_synthetic_job(job_id: UUID, body: EmptyJudgeMutation, request: Request):
        def authorize():
            with app.state.session_factory.begin() as db:
                owner = require_role(db, request, "administrator")
                broker.get_owned(db, owner, str(job_id), lock=True)
                if app.state.settings.judge_backend != "mock":
                    raise JudgeError("judge_runtime_unavailable", 503)
        await asyncio.to_thread(authorize)
        return await dispatch_mock(broker, app.state.judge_execution_backend, str(job_id))
