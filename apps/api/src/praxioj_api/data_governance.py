"""Bounded owner exports. Credentials, worker ownership and private rubrics stay private."""
from datetime import datetime
import json
from uuid import UUID

from fastapi import HTTPException, Request, Response
from pydantic import Field
from sqlalchemy import select

from .auth import user_public
from .models import (ConversationMessage, Evaluation, ProblemVersion, ProviderCall,
                     SolveSession, Submission, TraceEvent, WorkspaceFile, WorkspaceRun, utcnow)
from .retention import audit, trace_expired
from .quota_models import QuotaBucket
from .schemas import RequestModel


class ExportRequest(RequestModel):
    after_session_id: UUID | None = None
    limit: int = Field(default=25, ge=1, le=100)


class ExportWriter:
    """Bound the encoded output and rows while reading, without a giant JSON copy."""
    def __init__(self, max_bytes, max_rows):
        self.max_bytes, self.max_rows = max_bytes, max_rows
        self.data = bytearray(b"{")
        self.rows = 0
        self.fields = 0

    def append(self, value):
        encoded = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False,
            separators=(",", ":"), default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item)).encode()
        if len(self.data) + len(encoded) + 1 > self.max_bytes:
            raise HTTPException(413, "Export size limit exceeded; request fewer sessions")
        self.data.extend(encoded)

    def field(self, key, value):
        self.append((b"," if self.fields else b"") + json.dumps(key).encode() + b":")
        self.append(value)
        self.fields += 1

    def records(self, key, rows, project):
        self.append((b"," if self.fields else b"") + json.dumps(key).encode() + b":[")
        first = True
        for row in rows:
            self.rows += 1
            if self.rows > self.max_rows:
                raise HTTPException(413, "Export row limit exceeded; request fewer sessions")
            if not first:
                self.append(b",")
            self.append(project(row))
            first = False
        self.append(b"]")
        self.fields += 1

    def finish(self):
        self.append(b"}")
        return bytes(self.data)


def fields(row, names):
    return {name: getattr(row, name) for name in names.split()}


def export_account(db, user, settings, body):
    # User is locked by the authenticated POST guard. Lock only this page's
    # sessions in the same stable order as account erasure and reviewer batches.
    query = select(SolveSession).where(SolveSession.user_id == user.id)
    if body.after_session_id:
        query = query.where(SolveSession.id > str(body.after_session_id))
    sessions = list(db.scalars(query.order_by(SolveSession.id).limit(body.limit + 1).with_for_update()))
    more = len(sessions) > body.limit
    sessions = sessions[:body.limit]
    ids = [row.id for row in sessions]
    available = [row.id for row in sessions if not trace_expired(row)]
    availability = {row.id: "available" if row.id in available else "expired" for row in sessions}
    versions = {row.id: row for row in db.scalars(select(ProblemVersion)
        .where(ProblemVersion.id.in_({row.problem_version_id for row in sessions})))}
    writer = ExportWriter(settings.export_max_bytes, settings.export_max_rows)
    writer.field("format", "praxioj-account-export/1")
    writer.field("exported_at", utcnow())
    writer.field("profile", {**user_public(user), "created_at": user.created_at})
    writer.field("next_cursor", sessions[-1].id if more else None)
    writer.field("integrity_validation", "Checkpoints and original event hashes are preserved; this export is not an integrity certificate")
    writer.records("account_usage", db.scalars(select(QuotaBucket).where(QuotaBucket.scope == "user",
        QuotaBucket.subject == user.id).order_by(QuotaBucket.window_start).limit(settings.export_max_rows + 1)),
        lambda row: fields(row, "window_start model_calls tool_calls input_tokens output_tokens reserved_units uncertain_calls"))
    writer.records("sessions", sessions, lambda row: {
        **fields(row, "id status draft runtime_profile model_configuration created_at trace_retention_days trace_expires_at"),
        "problem_id": versions[row.problem_version_id].problem_id,
        "problem_version": versions[row.problem_version_id].version,
        "trace_availability": availability[row.id],
        "trace_head_sha256": row.trace_head_sha256,
        "next_sequence_number": row.next_sequence_number,
    })

    def rows(model, order, condition=None):
        condition = model.session_id.in_(ids) if condition is None else condition
        return db.scalars(select(model).where(condition).order_by(*order)
            .limit(settings.export_max_rows + 1).execution_options(yield_per=100))

    writer.records("messages", rows(ConversationMessage, (ConversationMessage.session_id, ConversationMessage.position)),
        lambda row: fields(row, "id session_id position role content tool_calls tool_call_id created_at"))
    writer.records("artifacts", rows(WorkspaceFile, (WorkspaceFile.session_id, WorkspaceFile.path)),
        lambda row: fields(row, "id session_id path content sha256 byte_size revision"))
    writer.records("submissions", rows(Submission, (Submission.session_id,)),
        lambda row: fields(row, "id session_id content content_sha256 artifacts created_at"))
    submissions = select(Submission.id).where(Submission.session_id.in_(ids))
    evaluations = db.execute(select(Evaluation, Submission.session_id).join(Submission,
        Submission.id == Evaluation.submission_id).where(Evaluation.submission_id.in_(submissions))
        .order_by(Submission.session_id).limit(settings.export_max_rows + 1).execution_options(yield_per=100))
    writer.records("evaluations", evaluations, lambda row: {
        **fields(row[0], "id submission_id result created_at"),
        "session_id": row[1], "trace_availability": availability[row[1]],
    })
    writer.records("runs", rows(WorkspaceRun, (WorkspaceRun.session_id, WorkspaceRun.created_at, WorkspaceRun.id)),
        lambda row: fields(row, "id session_id request_id status cancel_requested error created_at finished_at"))
    writer.records("provider_usage", rows(ProviderCall, (ProviderCall.session_id, ProviderCall.created_at, ProviderCall.id)),
        lambda row: fields(row, "id session_id run_id status input_tokens output_tokens estimated error_code created_at finished_at"))
    writer.records("traces", rows(TraceEvent, (TraceEvent.session_id, TraceEvent.sequence_number),
                                  TraceEvent.session_id.in_(available)), lambda row: row.envelope)
    payload = writer.finish()
    audit(db, "account_exported", actor_id=user.id, resource_id=user.id,
          session_count=len(sessions), row_count=writer.rows, byte_count=len(payload))
    return payload


def install_data_routes(app):
    @app.post("/api/auth/export")
    def account_export(body: ExportRequest, request: Request):
        from .security import require_recent_reauthentication
        with app.state.session_factory.begin() as db:
            user = require_recent_reauthentication(db, request)
            payload = export_account(db, user, app.state.settings, body)
        return Response(payload, media_type="application/json", headers={
            "Content-Disposition": 'attachment; filename="praxioj-account-export.json"',
        })
