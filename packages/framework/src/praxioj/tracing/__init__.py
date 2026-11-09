"""Observable event envelopes and collector contracts; never hidden AI reasoning."""

import re
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, JsonValue

from praxioj.core import DomainModel, utc_now


class EventType(StrEnum):
    SESSION_STARTED = "SESSION_STARTED"
    USER_MESSAGE = "USER_MESSAGE"
    ASSISTANT_MESSAGE = "ASSISTANT_MESSAGE"
    PROVIDER_CALL_STARTED = "PROVIDER_CALL_STARTED"
    PROVIDER_CALL_COMPLETED = "PROVIDER_CALL_COMPLETED"
    TOOL_CALL_AUTHORIZED = "TOOL_CALL_AUTHORIZED"
    SESSION_STATE_CHANGED = "SESSION_STATE_CHANGED"
    TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
    TOOL_CALL_COMPLETED = "TOOL_CALL_COMPLETED"
    ARTIFACT_UPDATED = "ARTIFACT_UPDATED"
    SUBMISSION_CREATED = "SUBMISSION_CREATED"
    EVALUATION_COMPLETED = "EVALUATION_COMPLETED"
    SESSION_ENDED = "SESSION_ENDED"
    ERROR = "ERROR"


class TraceEnvelope(DomainModel):
    event_id: UUID = Field(default_factory=uuid4)
    session_id: str = Field(min_length=1, max_length=128)
    sequence_number: int = Field(ge=1)
    event_type: EventType
    timestamp: AwareDatetime = Field(default_factory=utc_now)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    schema_version: Literal["1.0"] = "1.0"
    source: Literal["server", "external"] = "server"
    actor: str = "system"
    resource_ids: dict[str, str] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None, max_length=128)
    parent_event_id: str | None = Field(default=None, max_length=128)


class TraceReader(Protocol):
    """Caller must authorize the session before providing a trace to an evaluator."""

    def read(self, session_id: str, after_sequence: int = 0) -> list[TraceEnvelope]: ...


class TraceCollector(TraceReader, Protocol):
    def append(self, event: TraceEnvelope) -> None:
        """Persist once; reject reused IDs or non-contiguous session sequences."""
        ...


class InMemoryTraceCollector:
    """Standalone, single-threaded collector for SDK use; not durable storage."""

    def __init__(self) -> None:
        self._events: dict[str, list[TraceEnvelope]] = {}
        self._by_id: dict[UUID, TraceEnvelope] = {}

    def append(self, event: TraceEnvelope) -> None:
        safe = event.model_copy(deep=True, update={"payload": redact_payload(event.payload)})
        if event.event_id in self._by_id:
            if self._by_id[event.event_id] == safe:
                return  # Exact retries are idempotent; conflicting duplicates fail.
            raise ValueError("Event ID already exists with different content")
        events = self._events.setdefault(event.session_id, [])
        if event.sequence_number != len(events) + 1:
            raise ValueError("Trace sequence must be contiguous within its session")
        events.append(safe)
        self._by_id[safe.event_id] = safe

    def read(self, session_id: str, after_sequence: int = 0) -> list[TraceEnvelope]:
        return [item.model_copy(deep=True) for item in self._events.get(session_id, []) if item.sequence_number > after_sequence]


_SENSITIVE_KEY = re.compile(
    r"password|passwd|secret|authorization|api[_-]?key|cookie|credential|"
    r"(?:^|[_-])(?:access[_-]?|refresh[_-]?|auth[_-]?)?token(?:$|[_-])", re.I,
)
_TOKEN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._~+/-]+=*)", re.I)
_ASSIGNMENT = re.compile(r"\b((?:api[_-]?key|password|secret|access[_-]?token)\s*[=:]\s*)([^\s,;]+)", re.I)


def redact_payload(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Best effort only. Raw conversation storage requires a separate retention policy."""
    def walk(value: JsonValue, depth: int = 0) -> JsonValue:
        if depth > 20:
            return "[REDACTED: depth limit]"
        if isinstance(value, dict):
            return {key: "[REDACTED]" if _SENSITIVE_KEY.search(key) else walk(item, depth + 1) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item, depth + 1) for item in value]
        if isinstance(value, str):
            return _ASSIGNMENT.sub(r"\1[REDACTED]", _TOKEN.sub("[REDACTED]", value))
        return value

    return walk(payload)  # type: ignore[return-value]
