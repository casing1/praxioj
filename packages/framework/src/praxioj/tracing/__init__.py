"""Observable event envelopes and collector contracts; never hidden AI reasoning."""

import hashlib
import json
import re
from enum import StrEnum
from typing import Iterable, Literal, Protocol
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
    AUTHOR_EVENT = "AUTHOR_EVENT"


class TraceEnvelope(DomainModel):
    event_id: UUID = Field(default_factory=uuid4)
    session_id: str = Field(min_length=1, max_length=128)
    sequence_number: int = Field(ge=1)
    event_type: EventType
    timestamp: AwareDatetime = Field(default_factory=utc_now)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    schema_version: Literal["1.0", "1.1"] = "1.0"
    source: Literal["server", "external"] = "server"
    actor: str = "system"
    resource_ids: dict[str, str] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None, max_length=128)
    parent_event_id: str | None = Field(default=None, max_length=128)
    previous_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    event_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class TraceIntegrityResult(DomainModel):
    status: Literal["verified", "unverified", "invalid", "empty"]
    reason: str
    event_count: int = Field(ge=0)
    head_hash: str | None = None


def compute_event_hash(event: TraceEnvelope) -> str:
    """Hash the validated envelope, including its predecessor and all context.

    This deterministic encoding is versioned by schema_version. It is an
    integrity checksum, not a signature or proof against a database operator.
    """
    data = event.model_dump(mode="json", exclude={"event_hash"})
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def seal_trace_event(event: TraceEnvelope, previous_hash: str | None = None) -> TraceEnvelope:
    """Return a detached v1.1 envelope. Redact payloads before calling this."""
    data = event.model_dump(mode="json")
    data.update(schema_version="1.1", previous_hash=previous_hash, event_hash=None)
    sealed = TraceEnvelope.model_validate(data)
    sealed.event_hash = compute_event_hash(sealed)
    return sealed


def verify_trace_chain(events: Iterable[TraceEnvelope | dict], *, session_id: str | None = None,
                       anchor_hash: str | None = None, start_sequence: int = 1,
                       expected_head: str | None = None,
                       expected_next_sequence: int | None = None) -> TraceIntegrityResult:
    """Verify order, identity, session context and chained content checksums.

    A trusted head/count checkpoint is required to detect removal of a suffix.
    An optional trusted anchor permits a retained suffix to be checked. Neither
    anchor nor checkpoint is authenticated by this function. Legacy events are
    reported as unverified rather than retroactively certified.
    """
    if start_sequence < 1 or (expected_next_sequence is not None and expected_next_sequence < start_sequence):
        raise ValueError("Invalid trace sequence checkpoint")
    rows: list[TraceEnvelope] = []
    try:
        rows = [TraceEnvelope.model_validate(event) for event in events]
    except (TypeError, ValueError):
        return TraceIntegrityResult(status="invalid", reason="invalid_envelope", event_count=0)

    def result(status, reason, head=None):
        return TraceIntegrityResult(status=status, reason=reason, event_count=len(rows), head_hash=head)

    if expected_next_sequence is not None and start_sequence + len(rows) != expected_next_sequence:
        return result("invalid", "checkpoint_length_mismatch")
    if not rows:
        if expected_head is not None and expected_head != anchor_hash:
            return result("invalid", "checkpoint_head_mismatch")
        return result("empty", "no_events", anchor_hash)
    expected_session = session_id if session_id is not None else rows[0].session_id
    seen = set()
    for offset, event in enumerate(rows):
        if event.session_id != expected_session:
            return result("invalid", "session_mismatch")
        if event.event_id in seen:
            return result("invalid", "duplicate_event_id")
        seen.add(event.event_id)
        if event.sequence_number != start_sequence + offset:
            return result("invalid", "sequence_mismatch")
    if any(event.event_hash is None or event.schema_version != "1.1" for event in rows):
        return result("unverified", "legacy_unhashed_events")
    previous = anchor_hash
    for event in rows:
        if event.previous_hash != previous:
            return result("invalid", "predecessor_mismatch")
        try:
            digest = compute_event_hash(event)
        except (TypeError, ValueError):
            return result("invalid", "invalid_envelope")
        if event.event_hash != digest:
            return result("invalid", "content_hash_mismatch")
        previous = event.event_hash
    if expected_head is not None and previous != expected_head:
        return result("invalid", "checkpoint_head_mismatch")
    return result("verified", "chain_matches", previous)


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
