"""Explicit participant projections keep private evaluator configuration off the wire."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from praxioj.evaluation import EvaluationResult


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreate(RequestModel):
    problem_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    runtime_profile: Literal["mock", "compatible"] | None = None


class ContentRequest(RequestModel):
    content: str = Field(min_length=1, max_length=100_000)

    @field_validator("content")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Content must contain non-whitespace characters")
        return value


class RunRequest(ContentRequest):
    request_id: UUID


class DraftRequest(RequestModel):
    content: str = Field(max_length=100_000)


class RunError(BaseModel):
    code: str
    message: str


class RunView(BaseModel):
    id: str
    session_id: str
    request_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    error: RunError | None
    created_at: datetime
    finished_at: datetime | None
    job: dict | None = None


class PublicResource(BaseModel):
    name: str
    content: str
    media_type: str


class PublicLimits(BaseModel):
    max_messages: int
    max_message_chars: int
    max_submission_chars: int
    max_model_calls: int = 30
    max_tool_calls: int = 20
    max_total_tokens: int | None = None
    request_timeout_seconds: int = 30
    max_run_seconds: int = 90
    max_file_bytes: int = 16384
    max_workspace_bytes: int = 65536
    max_workspace_files: int = 8


class PublicSubmissionSpec(BaseModel):
    kind: Literal["text"]
    instructions: str


class PublicCriterion(BaseModel):
    id: str
    title: str
    description: str
    max_score: float


class PublicEvaluationSpec(BaseModel):
    evaluator_id: str
    evaluator_version: str
    criteria: list[PublicCriterion]


class ProblemPublic(BaseModel):
    id: str
    version: str
    title: str
    description: str
    category: str
    difficulty: str
    initial_resources: list[PublicResource]
    allowed_ai_capabilities: list[str]
    allowed_tools: list[str]
    ai_policy: dict = Field(default_factory=dict)
    tool_permissions: list[str] = Field(default_factory=list)
    resource_limits: PublicLimits
    submission: PublicSubmissionSpec
    evaluation: PublicEvaluationSpec
    trace_retention_days: int | None = None


class MessagePublic(BaseModel):
    id: str
    role: Literal["user", "assistant", "tool"]
    tool_calls: list[dict] = Field(default_factory=list)
    tool_call_id: str | None = None
    content: str
    created_at: datetime


class SessionDetail(BaseModel):
    id: str
    problem_id: str
    problem_version: str
    status: Literal["active", "submitted", "ended"]
    runtime_profile: str = "mock"
    model_configuration: dict = Field(default_factory=dict)
    active_run_id: str | None = None
    draft: str = ""
    latest_run: RunView | None = None
    messages: list[MessagePublic]
    submission_id: str | None
    evaluation_id: str | None
    created_at: datetime


class ChatResult(BaseModel):
    user_message: MessagePublic
    assistant_message: MessagePublic


class SubmissionReceipt(BaseModel):
    submission_id: str
    evaluation_id: str


class EvaluationPublic(EvaluationResult):
    session_id: str
    submission_id: str
    problem_id: str
    problem_version: str
    trace_availability: Literal["available", "expired", "unavailable"] = "available"


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    mode: Literal["local-development"] = "local-development"
    provider: Literal["mock"] = "mock"
