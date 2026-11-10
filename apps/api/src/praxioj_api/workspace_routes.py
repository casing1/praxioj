"""Owner-scoped local workspace endpoints; participant input never selects URLs."""
from hashlib import sha256
from fastapi import HTTPException, Request
from sqlalchemy import select
from praxioj.tracing import EventType
from .models import ConversationMessage, WorkspaceRun
from .schemas import DraftRequest, RunRequest, RunView, SessionDetail
from .security import require_user
from .services import active, append_trace, manifest_for, messages_for, owned_session, run_public, session_public
from .runs import TERMINAL, budget_code, profiles, scrub, usage_for, workspace_limits
from .workspace import DatabaseWorkspaceStore
from .jobs import cancel_locked, enqueue


def install_workspace_routes(app):
    @app.get("/api/runtime/options")
    def runtime_options():
        settings = app.state.settings
        return {"default_profile": settings.default_profile, "profiles": list(profiles(settings).values())}

    def owned_run(db, run_id, request, lock=False):
        owner = require_user(db, request)
        run = db.get(WorkspaceRun, run_id)
        if run is None:
            raise HTTPException(404, "Resource not found")
        session = owned_session(db, run.session_id, owner.id, lock=lock)
        if lock:
            db.refresh(run)
        return session, run

    @app.post("/api/sessions/{session_id}/runs", response_model=RunView, status_code=202)
    async def create_run(session_id: str, body: RunRequest, request: Request):
        with app.state.session_factory.begin() as db:
            owner = require_user(db, request)
            session = owned_session(db, session_id, owner.id, lock=True)
            # Compare the original request digest, never persist its unsanitized text.
            digest = sha256(body.content.encode("utf-8")).hexdigest()
            existing = db.scalar(select(WorkspaceRun).where(WorkspaceRun.session_id == session.id,
                                                           WorkspaceRun.request_id == str(body.request_id)))
            if existing:
                if existing.content_sha256 != digest:
                    raise HTTPException(409, "Request ID was already used with different content")
                return run_public(existing)
            active(session)
            _, manifest = manifest_for(db, session)
            limits = manifest.resource_limits
            if "chat" not in manifest.allowed_ai_capabilities:
                raise HTTPException(403, "AI chat is not allowed by this problem")
            if len(body.content) > limits.max_message_chars:
                raise HTTPException(422, "Message exceeds this problem's character limit")
            if session.user_message_count >= limits.max_messages:
                raise HTTPException(429, "This session's message limit has been reached")
            code = budget_code(usage_for(db, session, manifest), limits)
            if code:
                raise HTTPException(429, code)
            run = WorkspaceRun(session_id=session.id, request_id=str(body.request_id), content_sha256=digest)
            db.add(run)
            db.flush()
            session.active_run_id = run.id
            session.user_message_count += 1
            message = ConversationMessage(session_id=session.id, position=len(messages_for(db, session.id)) + 1,
                                          role="user", content=scrub(body.content, app.state.settings))
            db.add(message)
            db.flush()
            append_trace(db, session, EventType.USER_MESSAGE, {"content": message.content}, actor="participant",
                         resource_ids={"run_id": run.id, "message_id": message.id}, correlation_id=run.id)
            append_trace(db, session, EventType.SESSION_STATE_CHANGED, {"run_status": "queued"},
                         resource_ids={"run_id": run.id}, correlation_id=run.id)
            enqueue(db, session, run, limits.max_run_seconds)
            result = run_public(run)
        return result

    @app.get("/api/runs/{run_id}", response_model=RunView)
    async def get_run(run_id: str, request: Request):
        with app.state.session_factory() as db:
            _, run = owned_run(db, run_id, request)
            return run_public(run)

    @app.get("/api/sessions/{session_id}/runs", response_model=list[RunView])
    async def list_runs(session_id: str, request: Request):
        with app.state.session_factory() as db:
            owner = require_user(db, request)
            owned_session(db, session_id, owner.id)
            return [run_public(run) for run in db.scalars(select(WorkspaceRun).where(
                WorkspaceRun.session_id == session_id).order_by(WorkspaceRun.created_at, WorkspaceRun.id))]

    @app.post("/api/runs/{run_id}/cancel", response_model=RunView)
    async def cancel_run(run_id: str, request: Request):
        with app.state.session_factory.begin() as db:
            session, run = owned_run(db, run_id, request, lock=True)
            if run.status in TERMINAL:
                return run_public(run)
            cancel_locked(db, session, run)
        with app.state.session_factory() as db:
            return run_public(db.get(WorkspaceRun, run_id))

    @app.get("/api/sessions/{session_id}/usage")
    async def get_usage(session_id: str, request: Request):
        with app.state.session_factory() as db:
            owner = require_user(db, request)
            session = owned_session(db, session_id, owner.id)
            _, manifest = manifest_for(db, session)
            return usage_for(db, session, manifest)

    @app.get("/api/sessions/{session_id}/files")
    async def get_files(session_id: str, request: Request):
        with app.state.session_factory() as db:
            owner = require_user(db, request)
            session = owned_session(db, session_id, owner.id)
            _, manifest = manifest_for(db, session)
            return [f.model_dump(mode="json") for f in DatabaseWorkspaceStore(db, session.id, workspace_limits(manifest)).list_files()]

    @app.put("/api/sessions/{session_id}/draft")
    async def save_draft(session_id: str, body: DraftRequest, request: Request):
        with app.state.session_factory.begin() as db:
            owner = require_user(db, request)
            session = owned_session(db, session_id, owner.id, lock=True)
            from .retention import trace_expired
            if trace_expired(session):
                raise HTTPException(410, "This session's trace retention period has expired")
            if session.status != "active":
                raise HTTPException(409, "This session is closed")
            _, manifest = manifest_for(db, session)
            if len(body.content) > manifest.resource_limits.max_submission_chars:
                raise HTTPException(422, "Draft exceeds this problem's submission limit")
            session.draft = scrub(body.content, app.state.settings)
            return {"content": session.draft}

    @app.post("/api/sessions/{session_id}/end", response_model=SessionDetail)
    async def end_session(session_id: str, request: Request):
        with app.state.session_factory.begin() as db:
            owner = require_user(db, request)
            session = owned_session(db, session_id, owner.id, lock=True)
            active(session)
            session.status = "ended"
            append_trace(db, session, EventType.SESSION_STATE_CHANGED, {"session_status": "ended"}, actor="participant")
            append_trace(db, session, EventType.SESSION_ENDED, {"reason": "participant_ended"}, actor="participant")
            return session_public(db, session)
