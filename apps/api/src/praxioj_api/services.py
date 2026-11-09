"""Transactional platform orchestration around framework interfaces."""
from datetime import timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from praxioj.problems import ProblemManifest
from praxioj.tracing import EventType, TraceEnvelope, redact_payload
from .models import ConversationMessage, Evaluation, ProblemVersion, SolveSession, Submission, TraceEvent, WorkspaceRun


def manifest_for(db: Session, session: SolveSession) -> tuple[ProblemVersion, ProblemManifest]:
    version = db.get(ProblemVersion, session.problem_version_id)
    if version is None:
        raise RuntimeError("Session refers to a missing immutable problem version")
    return version, ProblemManifest.model_validate(version.manifest)


def owned_session(db: Session, session_id: str, user_id: str, *, lock: bool = False) -> SolveSession:
    query = select(SolveSession).where(SolveSession.id == session_id, SolveSession.user_id == user_id)
    if lock:
        query = query.with_for_update()
    session = db.scalar(query)
    if session is None:
        raise HTTPException(404, "Resource not found")
    return session


def active(session: SolveSession) -> None:
    if session.status != "active":
        raise HTTPException(409, "This session is closed")
    if session.active_run_id:
        raise HTTPException(409, "This session has an active AI run")


def messages_for(db: Session, session_id: str) -> list[ConversationMessage]:
    return list(db.scalars(select(ConversationMessage).where(
        ConversationMessage.session_id == session_id
    ).order_by(ConversationMessage.position)))


def message_public(message: ConversationMessage) -> dict:
    return {"id": message.id, "role": message.role, "content": message.content,
            "tool_calls": message.tool_calls, "tool_call_id": message.tool_call_id,
            "created_at": message.created_at.replace(tzinfo=timezone.utc) if message.created_at.tzinfo is None else message.created_at}


def session_public(db: Session, session: SolveSession) -> dict:
    version = db.get(ProblemVersion, session.problem_version_id)
    submission = db.scalar(select(Submission).where(Submission.session_id == session.id))
    evaluation = db.scalar(select(Evaluation).where(Evaluation.submission_id == submission.id)) if submission else None
    latest_run = db.scalar(select(WorkspaceRun).where(WorkspaceRun.session_id == session.id).order_by(WorkspaceRun.created_at.desc(), WorkspaceRun.id.desc()).limit(1))
    return {
        "runtime_profile": session.runtime_profile, "model_configuration": session.model_configuration,
        "active_run_id": session.active_run_id, "draft": session.draft,
        "latest_run": run_public(latest_run) if latest_run else None,
        "id": session.id, "problem_id": version.problem_id, "problem_version": version.version,
        "status": session.status, "messages": [message_public(m) for m in messages_for(db, session.id)],
        "submission_id": submission.id if submission else None,
        "evaluation_id": evaluation.id if evaluation else None,
        "created_at": session.created_at.replace(tzinfo=timezone.utc) if session.created_at.tzinfo is None else session.created_at,
    }


def append_trace(db: Session, session: SolveSession, event_type: EventType, payload: dict,
                 *, actor: str = "system", resource_ids: dict | None = None, correlation_id: str | None = None,
                 parent_event_id: str | None = None) -> TraceEnvelope:
    # The caller locks SolveSession before any mutation. PostgreSQL serializes writers;
    # the database unique constraint is an independent final check against duplicates.
    event = TraceEnvelope(
        session_id=session.id, sequence_number=session.next_sequence_number,
        event_type=event_type, payload=redact_payload(payload), actor=actor,
        resource_ids=resource_ids or {}, source="server",
        correlation_id=correlation_id, parent_event_id=parent_event_id,
    )
    session.next_sequence_number += 1
    db.add(TraceEvent(
        event_id=str(event.event_id), session_id=session.id,
        sequence_number=event.sequence_number, event_type=event.event_type.value,
        timestamp=event.timestamp, envelope=event.model_dump(mode="json"),
    ))
    db.flush()
    return event


def traces_for(db: Session, session_id: str) -> list[dict]:
    return list(db.scalars(select(TraceEvent.envelope).where(
        TraceEvent.session_id == session_id
    ).order_by(TraceEvent.sequence_number)))


def run_public(run: WorkspaceRun) -> dict:
    return {"id": run.id, "session_id": run.session_id, "request_id": run.request_id,
            "status": run.status, "error": run.error, "created_at": run.created_at,
            "finished_at": run.finished_at}
