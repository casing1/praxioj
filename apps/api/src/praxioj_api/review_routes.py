"""Authorized evaluation review projections and minimal administrative audit views."""
from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from .models import Evaluation, Problem, ProblemVersion, SolveSession, Submission
from .retention_models import AuditRecord
from .retention import audit, erase_account, purge_expired, trace_status, visible_trace
from .security import can_manage_problem, require_role, require_user
from .services import owned_session


def review_session(db, request, session_id):
    user = require_role(db, request, "administrator", "author")
    session = db.get(SolveSession, session_id)
    version = db.get(ProblemVersion, session.problem_version_id) if session else None
    problem = db.get(Problem, version.problem_id) if version else None
    if not problem or not can_manage_problem(user, problem):
        raise HTTPException(404, "Resource not found")
    return user, session


def review_projection(event):
    # Reviewers need event evidence, not unrestricted conversation/file content.
    keys = {"status", "code", "allowed", "name", "model", "usage", "path", "sha256",
            "byte_size", "revision", "run_status", "session_status", "score", "maximum_score"}
    return {"event_id": event["event_id"], "sequence_number": event["sequence_number"],
            "event_type": event["event_type"], "actor": event["actor"], "timestamp": event["timestamp"],
            "resource_ids": event["resource_ids"], "correlation_id": event.get("correlation_id"),
            "payload": {k: v for k, v in event["payload"].items() if k in keys}}


def install_review_routes(app):
    @app.get("/api/sessions/{session_id}/trace/integrity")
    def integrity(session_id: str, request: Request):
        with app.state.session_factory() as db:
            owner = require_user(db, request)
            return trace_status(db, owned_session(db, session_id, owner.id))

    @app.get("/api/review/sessions/{session_id}/trace")
    def review_trace(session_id: str, request: Request):
        with app.state.session_factory.begin() as db:
            user, session = review_session(db, request, session_id)
            status = trace_status(db, session)
            events = [] if status["status"] == "expired" else [review_projection(e) for e in visible_trace(db, session)]
            audit(db, "trace_reviewed", user.id, session.id, event_count=len(events))
            return {"events": events, "integrity": status, "projection": "evaluation-metadata"}

    @app.get("/api/review/problems/{problem_id}/evaluations")
    def review_evaluations(problem_id: str, request: Request):
        with app.state.session_factory.begin() as db:
            user = require_role(db, request, "administrator", "author")
            problem = db.get(Problem, problem_id)
            if not problem or not can_manage_problem(user, problem):
                raise HTTPException(404, "Resource not found")
            rows = db.execute(select(Evaluation, SolveSession).join(Submission, Evaluation.submission_id == Submission.id)
                .join(SolveSession, Submission.session_id == SolveSession.id)
                .join(ProblemVersion, SolveSession.problem_version_id == ProblemVersion.id)
                .where(ProblemVersion.problem_id == problem_id).order_by(SolveSession.id).limit(100)
                .with_for_update(of=SolveSession)).all()
            audit(db, "evaluations_reviewed", user.id, result_count=len(rows))
            return [{"evaluation_id": evaluation.id, "session_id": session.id, "result": evaluation.result,
                     "trace_integrity": trace_status(db, session)} for evaluation, session in rows]

    @app.get("/api/admin/audit")
    def audit_records(request: Request):
        with app.state.session_factory() as db:
            require_role(db, request, "administrator")
            records = db.scalars(select(AuditRecord).order_by(AuditRecord.created_at.desc()).limit(100))
            return [{"id": row.id, "action": row.action, "actor_id": row.actor_id, "resource_id": row.resource_id,
                     "details": row.details, "created_at": row.created_at} for row in records]

    @app.post("/api/admin/retention/purge")
    def purge(request: Request):
        with app.state.session_factory.begin() as db:
            user = require_role(db, request, "administrator")
            audit(db, "retention_requested", user.id)
        return {"purged_sessions": purge_expired(app.state.session_factory, app.state.settings)}

    @app.post("/api/auth/delete")
    def delete_account(request: Request, response: Response):
        with app.state.session_factory.begin() as db:
            user = require_user(db, request)
            result = erase_account(db, user)
        for name in (app.state.settings.cookie_name, app.state.settings.csrf_cookie_name):
            response.delete_cookie(name, path="/", secure=app.state.settings.cookie_secure, httponly=True, samesite="strict")
        return result
