"""Authenticated local development API; durable execution lives in a separate worker."""
import asyncio
from datetime import timedelta
from contextlib import asynccontextmanager
from hashlib import sha256
import platform
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from praxioj.core import Artifact
from praxioj.evaluation import EvaluationEngine, EvaluationInput, EvaluationResult, ResourceUsageSnapshot, SubmissionData
from praxioj.problems import ProblemManifest, public_problem
from praxioj.runtime import AIRuntime, Message, MockProvider, ModelConfig, RuntimeContext
from praxioj.tracing import EventType, TraceEnvelope

from .database import make_engine, session_factory
from .models import ConversationMessage, Evaluation, ProblemVersion, SolveSession, Submission, ProviderCall, WorkspaceFile, utcnow
from .schemas import ChatResult, ContentRequest, EvaluationPublic, HealthResponse, ProblemPublic, SessionCreate, SessionDetail, SubmissionReceipt
from .security import LocalDevelopmentGuard, require_user
from .auth_routes import install_auth_routes
from .services import active, append_trace, manifest_for, message_public, messages_for, owned_session, session_public, traces_for
from .settings import Settings
from .runs import RunManager, configure_session, scrub, workspace_limits, usage_for, budget_code
from .workspace import DatabaseWorkspaceStore
from .workspace_routes import install_workspace_routes
from .review_routes import install_review_routes
from .retention import trace_expired, visible_trace


def get_db(request: Request):
    with request.app.state.session_factory() as db:
        yield db


Db = Annotated[Session, Depends(get_db)]


def create_app(settings: Settings | None = None, *, database_url: str | None = None) -> FastAPI:
    settings = settings or Settings(**({"database_url": database_url} if database_url else {}))
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="PraxiOJ — Local Development API", version="0.3.0", lifespan=lifespan,
        description="Authenticated AI workspace with a PostgreSQL worker queue. Development preview; bind to loopback.",
        docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory(engine)
    app.state.runtime = AIRuntime(MockProvider())
    app.state.evaluator = EvaluationEngine()
    app.state.run_manager = RunManager(app)
    install_workspace_routes(app)
    install_auth_routes(app)
    install_review_routes(app)
    app.add_middleware(LocalDevelopmentGuard, settings=settings)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, exc):
        # Validation input/ctx can contain a submitted password, token, or draft.
        return JSONResponse({"detail": [{"loc": e["loc"], "type": e["type"], "msg": e["msg"]}
                                       for e in exc.errors()]}, status_code=422)

    @app.exception_handler(IntegrityError)
    async def integrity_error(_request, _exc):
        return JSONResponse({"detail": "Concurrent update conflicted; reload the session before retrying"}, status_code=409)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request, _exc):
        return JSONResponse({"detail": "Database unavailable or not migrated"}, status_code=503)

    @app.get("/health", response_model=HealthResponse, include_in_schema=False)
    @app.get("/api/health", response_model=HealthResponse)
    def health(db: Db):
        db.execute(text("SELECT 1"))
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        if revision != "0005_trace":
            raise HTTPException(503, "Database migrations are required")
        return HealthResponse()

    @app.get("/api/problems", response_model=list[ProblemPublic])
    def list_problems(db: Db):
        versions = db.scalars(select(ProblemVersion).order_by(ProblemVersion.created_at.desc(), ProblemVersion.id.desc()))
        latest: dict[str, dict] = {}
        for version in versions:
            if version.problem_id not in latest:
                latest[version.problem_id] = public_problem(ProblemManifest.model_validate(version.manifest))
        return [latest[key] for key in sorted(latest)]

    @app.get("/api/problems/{problem_id}", response_model=ProblemPublic)
    def get_problem(problem_id: str, db: Db, version: str | None = None):
        query = select(ProblemVersion).where(ProblemVersion.problem_id == problem_id)
        if version is not None:
            query = query.where(ProblemVersion.version == version)
        row = db.scalar(query.order_by(ProblemVersion.created_at.desc(), ProblemVersion.id.desc()).limit(1))
        if row is None:
            raise HTTPException(404, "Problem version not found")
        return public_problem(ProblemManifest.model_validate(row.manifest))

    @app.post("/api/sessions", response_model=SessionDetail, status_code=201)
    def create_session(body: SessionCreate, request: Request, response: Response, db: Db):
        with db.begin():
            version = db.scalar(select(ProblemVersion).where(
                ProblemVersion.problem_id == body.problem_id, ProblemVersion.version == body.version,
            ))
            if version is None:
                raise HTTPException(404, "Problem version not found")
            owner = require_user(db, request)
            manifest = ProblemManifest.model_validate(version.manifest)
            profile_id, model_config, snapshot = configure_session(settings, manifest, body.runtime_profile)
            retention_days = min(manifest.trace_retention_days or settings.trace_retention_days, settings.trace_retention_max_days)
            session = SolveSession(user_id=owner.id, problem_version_id=version.id,
                                   model_configuration=model_config, runtime_profile=profile_id, profile_snapshot=snapshot,
                                   trace_retention_days=retention_days, trace_expires_at=utcnow() + timedelta(days=retention_days))
            db.add(session)
            db.flush()
            store = DatabaseWorkspaceStore(db, session.id, workspace_limits(manifest))
            try:
                for resource in manifest.initial_resources:
                    store.write(resource.name, scrub(resource.content, settings))
            except ValueError:
                raise HTTPException(422, "Initial resources exceed the logical workspace policy") from None
            append_trace(db, session, EventType.SESSION_STARTED, {
                "problem_id": version.problem_id, "problem_version": version.version,
                "manifest_sha256": version.manifest_sha256, "model_configuration": session.model_configuration,
                "evaluator_id": manifest.evaluation.evaluator_id,
                "evaluator_version": manifest.evaluation.evaluator_version,
                "environment": {"mode": "local-development", "execution_backend": "unavailable",
                                "framework_version": "0.1.0", "platform_version": "0.3.0", "python": platform.python_version()},
                "trace_retention_days": retention_days, "trace_expires_at": session.trace_expires_at.isoformat(),
            }, actor="participant", resource_ids={"problem_version_id": version.id})
            result = session_public(db, session)
        return result

    @app.get("/api/sessions/{session_id}", response_model=SessionDetail)
    def get_session(session_id: str, request: Request, db: Db):
        owner = require_user(db, request)
        return session_public(db, owned_session(db, session_id, owner.id))

    @app.post("/api/sessions/{session_id}/messages", response_model=ChatResult)
    def send_message(session_id: str, body: ContentRequest, request: Request, db: Db):
        with db.begin():
            owner = require_user(db, request)
            session = owned_session(db, session_id, owner.id, lock=True)
            active(session)
            _version, manifest = manifest_for(db, session)
            if session.runtime_profile != "mock" or manifest.allowed_tools:
                raise HTTPException(409, "Use the asynchronous /runs endpoint for this session")
            code = budget_code(usage_for(db, session, manifest), manifest.resource_limits)
            if code:
                raise HTTPException(429, code)
            if "chat" not in manifest.allowed_ai_capabilities:
                raise HTTPException(403, "AI chat is not allowed by this problem")
            if len(body.content) > manifest.resource_limits.max_message_chars:
                raise HTTPException(422, "Message exceeds this problem's character limit")
            if session.user_message_count >= manifest.resource_limits.max_messages:
                raise HTTPException(429, "This session's message limit has been reached")
            content = scrub(body.content, settings)
            history = messages_for(db, session.id)
            runtime_messages = [Message(role=m.role, content=m.content) for m in history]
            runtime_messages.append(Message(role="user", content=content))
            call = ProviderCall(session_id=session.id)
            db.add(call)
            db.flush()
            try:
                # Sync routes execute in FastAPI's thread pool. Only the deterministic
                # local mock is wired here; future network providers need async orchestration.
                reply = asyncio.run(request.app.state.runtime.respond(
                    runtime_messages, ModelConfig.model_validate(session.model_configuration),
                    manifest.resource_limits.max_messages,
                    RuntimeContext(session_id=session.id, allowed_capabilities=manifest.allowed_ai_capabilities,
                                   allowed_tools=manifest.allowed_tools),
                ))
            except Exception:
                call.status, call.error_code, call.finished_at = "failed", "provider_failed", utcnow()
                append_trace(db, session, EventType.ERROR, {"stage": "ai_runtime", "code": "provider_failed"})
                result = JSONResponse({"detail": "AI provider failed; the message was not stored"}, status_code=502)
            else:
                call.status, call.finished_at = "completed", utcnow()
                call.input_tokens, call.output_tokens, call.estimated = reply.usage.input_tokens, reply.usage.output_tokens, reply.usage.estimated
                user_message = ConversationMessage(session_id=session.id, position=len(history) + 1,
                                                   role="user", content=content)
                assistant_message = ConversationMessage(session_id=session.id, position=len(history) + 2,
                                                        role="assistant", content=scrub(reply.content, settings))
                db.add_all([user_message, assistant_message])
                session.user_message_count += 1
                db.flush()
                append_trace(db, session, EventType.USER_MESSAGE, {"content": content},
                             actor="participant", resource_ids={"message_id": user_message.id})
                append_trace(db, session, EventType.ASSISTANT_MESSAGE,
                             {"content": assistant_message.content, "model": reply.model, "usage": reply.usage.model_dump(mode="json")},
                             actor="assistant", resource_ids={"message_id": assistant_message.id})
                result = {"user_message": message_public(user_message), "assistant_message": message_public(assistant_message)}
        return result

    @app.get("/api/sessions/{session_id}/trace", response_model=list[TraceEnvelope])
    def get_trace(session_id: str, request: Request, db: Db):
        owner = require_user(db, request)
        session = owned_session(db, session_id, owner.id)
        return visible_trace(db, session)

    @app.post("/api/sessions/{session_id}/submissions", response_model=SubmissionReceipt, status_code=201)
    def submit(session_id: str, body: ContentRequest, request: Request, db: Db):
        with db.begin():
            owner = require_user(db, request)
            session = owned_session(db, session_id, owner.id, lock=True)
            active(session)
            version, manifest = manifest_for(db, session)
            if len(body.content) > manifest.resource_limits.max_submission_chars:
                raise HTTPException(422, "Submission exceeds this problem's character limit")
            content = scrub(body.content, settings)
            files = list(db.scalars(select(WorkspaceFile).where(WorkspaceFile.session_id == session.id).order_by(WorkspaceFile.path)))
            artifacts = [Artifact(id=f.id, name=f.path.rsplit("/", 1)[-1][:128], content=f.content, sha256=f.sha256) for f in files]
            submission = Submission(session_id=session.id, content=content,
                                    content_sha256=sha256(content.encode("utf-8")).hexdigest(),
                                    artifacts=[{**a.model_dump(mode="json"), "path": f.path} for a, f in zip(artifacts, files)])
            db.add(submission)
            db.flush()
            metadata = {"submission_id": submission.id, "sha256": submission.content_sha256,
                        "problem_id": version.problem_id, "problem_version": version.version}
            append_trace(db, session, EventType.ARTIFACT_UPDATED, metadata, actor="participant",
                         resource_ids={"submission_id": submission.id})
            append_trace(db, session, EventType.SUBMISSION_CREATED, metadata, actor="participant",
                         resource_ids={"submission_id": submission.id})
            try:
                usage = usage_for(db, session, manifest)
                result = request.app.state.evaluator.evaluate(EvaluationInput(
                    problem=manifest,
                    submission=SubmissionData(id=submission.id, content=submission.content, sha256=submission.content_sha256),
                    artifacts=artifacts,
                    trace=[TraceEnvelope.model_validate(e) for e in traces_for(db, session.id)],
                    usage=ResourceUsageSnapshot(user_messages=session.user_message_count,
                        model_calls=usage["model_calls"], tool_calls=usage["tool_calls"],
                        input_tokens=usage["input_tokens"] if usage["usage_complete"] else None,
                        output_tokens=usage["output_tokens"] if usage["usage_complete"] else None,
                        usage_complete=usage["usage_complete"], estimated=usage["estimated"]),
                ))
            except Exception:
                result = EvaluationResult(
                    id=uuid4(), status="failed", score=None, maximum_score=None, criteria=[],
                    feedback=["The trusted evaluator failed. Contact the local operator."], evidence=[],
                    evaluator_id=manifest.evaluation.evaluator_id, evaluator_version=manifest.evaluation.evaluator_version,
                )
            if result.status == "failed":
                append_trace(db, session, EventType.ERROR, {"stage": "evaluation", "code": "evaluator_failed"})
            evaluation = Evaluation(id=str(result.id), submission_id=submission.id, result=result.model_dump(mode="json"))
            db.add(evaluation)
            db.flush()
            append_trace(db, session, EventType.EVALUATION_COMPLETED,
                         {"evaluation_id": evaluation.id, "status": result.status, "score": result.score,
                          "maximum_score": result.maximum_score, "evaluator_id": result.evaluator_id,
                          "evaluator_version": result.evaluator_version}, resource_ids={"evaluation_id": evaluation.id})
            session.status = "submitted"
            session.draft = submission.content
            append_trace(db, session, EventType.SESSION_ENDED, {"reason": "final_submission"})
            receipt = {"submission_id": submission.id, "evaluation_id": evaluation.id}
        return receipt

    @app.get("/api/evaluations/{evaluation_id}", response_model=EvaluationPublic)
    def get_evaluation(evaluation_id: str, request: Request, db: Db):
        owner = require_user(db, request)
        row = db.execute(select(Evaluation, Submission, SolveSession, ProblemVersion)
                         .join(Submission, Evaluation.submission_id == Submission.id)
                         .join(SolveSession, Submission.session_id == SolveSession.id)
                         .join(ProblemVersion, SolveSession.problem_version_id == ProblemVersion.id)
                         .where(Evaluation.id == evaluation_id, SolveSession.user_id == owner.id)).first()
        if row is None:
            raise HTTPException(404, "Resource not found")
        evaluation, submission, session, version = row
        return {**evaluation.result, "session_id": session.id, "submission_id": submission.id,
                "problem_id": version.problem_id, "problem_version": version.version,
                "trace_availability": "expired" if trace_expired(session) else "available"}

    return app


app = create_app()
