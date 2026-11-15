"""Synthetic Runner channel contracts, not network authentication or OS isolation.

The caller observes the Mock transport identity through trusted construction.
Payload identity is only a binding to that observation, never authentication.
Opaque grants are supplied by the Platform; the fixed backend receives only the
ExecutionRequest. No process, filesystem collector or network client exists here.
"""
from datetime import datetime
from secrets import compare_digest
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, StrictInt, field_validator, model_validator

from .backends import MockJudgeBackend
from .protocol import (CleanupResult, Digest, ExecutionRequest, ExecutionValidationError,
    Identifier, ProtocolModel, RuntimeAvailability, _parse, canonical_json, parse_execution_request,
    request_digest)

RUNNER_PROTOCOL_VERSION = "1.0"
RunnerOperation = Literal["heartbeat", "submit_result", "cancel"]


class RunnerChannelError(ValueError):
    """Controlled error codes only; no raw wire message or secret is included."""


class RunnerIdentity(ProtocolModel):
    runner_id: Identifier = Field(max_length=64)
    transport: Literal["in_memory_mock"] = "in_memory_mock"
    synthetic_only: Literal[True] = True
    host_isolation_verified: Literal[False] = False


class RunnerBinding(ProtocolModel):
    request_id: UUID
    job_id: UUID
    attempt_id: UUID
    fence: StrictInt = Field(ge=1, le=2_147_483_647)
    request_digest: Digest
    input_digest: Digest
    policy_digest: Digest
    runtime_image_digest: Digest


def runner_binding(request: ExecutionRequest) -> RunnerBinding:
    request = parse_execution_request(request)
    return RunnerBinding(request_id=request.request_id, job_id=request.job_id, attempt_id=request.attempt_id,
        fence=request.fence, request_digest=request_digest(request), input_digest=request.input_digest,
        policy_digest=request.policy_digest, runtime_image_digest=request.runtime_image.digest)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Runner timestamp requires a timezone")
    return value


class RunnerGrant(ProtocolModel):
    grant_id: UUID
    token: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$", repr=False)
    audience: Identifier = Field(max_length=64)
    operation: RunnerOperation
    binding: RunnerBinding
    expires_at: datetime

    _expiry_aware = field_validator("expires_at")(_aware)


class RunnerDispatch(ProtocolModel):
    protocol_version: Literal[RUNNER_PROTOCOL_VERSION]
    identity: RunnerIdentity
    request: ExecutionRequest = Field(repr=False)
    grants: tuple[RunnerGrant, ...] = Field(min_length=3, max_length=3, repr=False)

    @model_validator(mode="after")
    def bound_grants(self):
        binding = runner_binding(self.request)
        if {item.operation for item in self.grants} != {"heartbeat", "submit_result", "cancel"}:
            raise ValueError("Dispatch requires three distinct operation grants")
        if len({item.grant_id for item in self.grants}) != 3 or len({item.token for item in self.grants}) != 3:
            raise ValueError("Dispatch grants must have distinct identities")
        for grant in self.grants:
            if grant.binding != binding or grant.audience != self.identity.runner_id or grant.expires_at > self.request.deadline:
                raise ValueError("Dispatch grant binding mismatch")
        return self


class RunnerMessage(ProtocolModel):
    protocol_version: Literal[RUNNER_PROTOCOL_VERSION]
    message_id: UUID
    identity: RunnerIdentity
    grant: RunnerGrant = Field(repr=False)

    @model_validator(mode="after")
    def audience_matches(self):
        if self.identity.runner_id != self.grant.audience:
            raise ValueError("Runner audience mismatch")
        return self


class RunnerHeartbeat(RunnerMessage):
    kind: Literal["heartbeat"]

    @model_validator(mode="after")
    def heartbeat_operation(self):
        if self.grant.operation != "heartbeat":
            raise ValueError("Wrong heartbeat grant operation")
        return self


class RunnerHeartbeatAck(ProtocolModel):
    protocol_version: Literal[RUNNER_PROTOCOL_VERSION]
    message_id: UUID
    identity: RunnerIdentity
    grant: RunnerGrant = Field(repr=False)
    heartbeat_at: datetime
    lease_expires_at: datetime
    expires_at: datetime
    deadline_at: datetime

    _times_aware = field_validator("heartbeat_at", "lease_expires_at", "expires_at", "deadline_at")(_aware)

    @model_validator(mode="after")
    def renewal_bounds(self):
        if (self.grant.operation != "heartbeat" or self.grant.audience != self.identity.runner_id
                or not self.heartbeat_at < self.lease_expires_at <= self.expires_at <= self.deadline_at
                or self.grant.expires_at != self.expires_at):
            raise ValueError("Invalid server renewal bounds")
        return self


class RunnerResultSubmission(RunnerMessage):
    kind: Literal["submit_result"]
    # This is deliberately untrusted, freshly bounded JSON. The Broker performs
    # M5 schema, digest, artifact and assessment validation before persistence.
    result: dict = Field(repr=False)

    @model_validator(mode="after")
    def result_operation(self):
        if self.grant.operation != "submit_result":
            raise ValueError("Wrong result grant operation")
        return self


class RunnerCancellation(RunnerMessage):
    kind: Literal["cancel"]

    @model_validator(mode="after")
    def cancellation_operation(self):
        if self.grant.operation != "cancel":
            raise ValueError("Wrong cancellation grant operation")
        return self


class RunnerCancellationAck(ProtocolModel):
    protocol_version: Literal[RUNNER_PROTOCOL_VERSION]
    message_id: UUID
    identity: RunnerIdentity
    binding: RunnerBinding
    cleanup: CleanupResult

    @model_validator(mode="after")
    def synthetic_cleanup(self):
        if self.cleanup != CleanupResult(status="not_required", reason="synthetic_no_resources"):
            raise ValueError("Mock cleanup is not OS cleanup evidence")
        return self


class RunnerRuntimeStatus(ProtocolModel):
    protocol_version: Literal[RUNNER_PROTOCOL_VERSION]
    identity: RunnerIdentity
    availability: RuntimeAvailability


def parse_runner_message(model, raw):
    """Fresh validation with M5 duplicate-key, UTF-8, depth/node and 64 KiB bounds."""
    if model not in {RunnerDispatch, RunnerHeartbeat, RunnerHeartbeatAck, RunnerResultSubmission,
                     RunnerCancellation, RunnerCancellationAck, RunnerRuntimeStatus}:
        raise ExecutionValidationError("unsupported_runner_message")
    return _parse(model, raw)


class MockRunnerTransport:
    """One bounded in-process synthetic attempt; no remote endpoint is exposed.

    The identity property is observed from a trusted constructor by the Broker
    adapter. It is not a credential, TLS identity or remotely verified claim.
    """
    def __init__(self, runner_id="mock-runner", *, backend=None):
        self.identity = RunnerIdentity(runner_id=runner_id)
        self._backend = backend if backend is not None else MockJudgeBackend()
        self._dispatch = None
        self._heartbeat = None
        self._pending_heartbeat = None
        self._result_sent = False
        self._cancelled = False
        self._executing = False

    def availability(self) -> bytes:
        request = self._dispatch.request if self._dispatch is not None else None
        return canonical_json(RunnerRuntimeStatus(protocol_version=RUNNER_PROTOCOL_VERSION, identity=self.identity,
            availability=self._backend.availability(request)))

    def open(self, raw) -> None:
        if self._dispatch is not None or self._executing:
            raise RunnerChannelError("runner_channel_busy")
        dispatch = parse_runner_message(RunnerDispatch, raw)
        if dispatch.identity != self.identity:
            raise RunnerChannelError("runner_identity_mismatch")
        self._dispatch = dispatch
        self._heartbeat = next(item for item in dispatch.grants if item.operation == "heartbeat")
        self._result_sent = self._cancelled = False

    def _active(self):
        if self._dispatch is None:
            raise RunnerChannelError("runner_channel_closed")
        return self._dispatch

    def heartbeat(self) -> bytes:
        self._active()
        if self._cancelled or self._result_sent:
            raise RunnerChannelError("runner_attempt_finished")
        if self._pending_heartbeat is not None:
            raise RunnerChannelError("heartbeat_ack_required")
        message = RunnerHeartbeat(protocol_version=RUNNER_PROTOCOL_VERSION, kind="heartbeat", message_id=uuid4(),
            identity=self.identity, grant=self._heartbeat)
        self._pending_heartbeat = message.message_id
        return canonical_json(message)

    def acknowledge(self, raw) -> None:
        dispatch = self._active()
        ack = parse_runner_message(RunnerHeartbeatAck, raw)
        if (self._pending_heartbeat is None or ack.message_id != self._pending_heartbeat
                or ack.identity != self.identity or ack.grant.binding != runner_binding(dispatch.request)
                or ack.grant.grant_id == self._heartbeat.grant_id or ack.grant.token == self._heartbeat.token
                or ack.deadline_at != dispatch.request.deadline):
            raise RunnerChannelError("heartbeat_ack_mismatch")
        self._heartbeat, self._pending_heartbeat = ack.grant, None

    async def execute(self) -> bytes:
        dispatch = self._active()
        if self._result_sent or self._executing:
            raise RunnerChannelError("runner_result_already_sent")
        self._executing = True
        # The backend is a fixed synthetic fixture and sees no channel grants.
        try:
            was_cancelled = self._cancelled
            raw = await (MockJudgeBackend("cancelled") if was_cancelled else self._backend).execute(dispatch.request)
            if self._cancelled and not was_cancelled:
                raw = await MockJudgeBackend("cancelled").execute(dispatch.request)
            if self._dispatch is not dispatch:
                raise RunnerChannelError("runner_channel_closed")
            grant = next(item for item in dispatch.grants if item.operation == "submit_result")
            message = RunnerResultSubmission(protocol_version=RUNNER_PROTOCOL_VERSION, kind="submit_result",
                message_id=uuid4(), identity=self.identity, grant=grant, result=raw)
            wire = canonical_json(message)
            self._result_sent = True
            return wire
        finally:
            self._executing = False

    def cancel(self, raw) -> bytes:
        dispatch = self._active()
        message = parse_runner_message(RunnerCancellation, raw)
        expected = next(item for item in dispatch.grants if item.operation == "cancel")
        if (self._cancelled or message.identity != self.identity
                or message.grant.model_dump(exclude={"token"}) != expected.model_dump(exclude={"token"})
                or not compare_digest(message.grant.token, expected.token)):
            raise RunnerChannelError("runner_cancellation_invalid")
        self._cancelled = True
        return canonical_json(RunnerCancellationAck(protocol_version=RUNNER_PROTOCOL_VERSION,
            message_id=message.message_id, identity=self.identity, binding=runner_binding(dispatch.request),
            cleanup=CleanupResult(status="not_required", reason="synthetic_no_resources")))

    def cancellation_poll(self) -> bytes:
        """Ask for a persisted cancellation signal; never cancel Broker state."""
        dispatch = self._active()
        grant = next(item for item in dispatch.grants if item.operation == "cancel")
        return canonical_json(RunnerCancellation(protocol_version=RUNNER_PROTOCOL_VERSION, kind="cancel",
            message_id=uuid4(), identity=self.identity, grant=grant))

    def close(self) -> None:
        self._dispatch = self._heartbeat = self._pending_heartbeat = None
        self._cancelled = self._result_sent = False
