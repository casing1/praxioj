"""Trusted Broker adapter for the in-memory synthetic Runner channel.

No HTTP endpoint or operational remote authentication is provided. The caller
obtains observed_identity from a trusted MockRunnerTransport constructor, never
from an untrusted message. Only bounded wire bytes cross into that transport;
the Broker, DB/settings and original JudgeLease remain in this adapter.
"""
from dataclasses import dataclass
from hashlib import sha256
from secrets import compare_digest, token_urlsafe
from threading import RLock
from uuid import uuid4

from praxioj.execution import (RUNNER_PROTOCOL_VERSION, RunnerCancellation, RunnerCancellationAck,
    RunnerChannelError, RunnerDispatch, RunnerGrant, RunnerHeartbeat, RunnerHeartbeatAck,
    RunnerIdentity, RunnerResultSubmission, RunnerRuntimeStatus, canonical_digest, canonical_json,
    parse_runner_message, runner_binding)


@dataclass(frozen=True)
class _GrantRecord:
    metadata_digest: str
    token_digest: str


def _token_digest(token):
    return sha256(token.encode("ascii")).hexdigest()


def _metadata_digest(grant):
    return canonical_digest(grant.model_dump(mode="json", exclude={"token"}))


class JudgeRunnerGateway:
    """One attempt, at most three active grant hashes, no global registry.

    Restart or close loses the channel grants; the durable Broker lease must then
    expire/recover. The caller cannot reconstruct the original capability from
    persisted hashes. This is fail-closed test orchestration, not remote hosting.
    """
    def __init__(self, broker, lease, identity: RunnerIdentity):
        if lease.worker_id != identity.runner_id:
            raise RunnerChannelError("runner_worker_mismatch")
        self._broker, self._lease, self._identity = broker, lease, identity
        self._binding = runner_binding(lease.request)
        self._lock = RLock()
        self._grants = {}
        self._started = False
        self._closed = False
        self._cancel_message_id = None

    @property
    def active_grants(self):
        return len(self._grants)

    def _observe(self, observed_identity):
        if observed_identity != self._identity:
            raise RunnerChannelError("runner_identity_mismatch")

    def _issue(self, operation, expiry):
        grant = RunnerGrant(grant_id=uuid4(), token=token_urlsafe(32), audience=self._identity.runner_id,
            operation=operation, binding=self._binding, expires_at=expiry)
        self._grants[operation] = _GrantRecord(_metadata_digest(grant), _token_digest(grant.token))
        return grant

    def start(self, runtime_wire, *, observed_identity) -> bytes:
        with self._lock:
            self._observe(observed_identity)
            if self._closed or self._started:
                raise RunnerChannelError("runner_channel_already_started")
            runtime = parse_runner_message(RunnerRuntimeStatus, runtime_wire)
            if runtime.identity != self._identity:
                raise RunnerChannelError("runner_identity_mismatch")
            if (runtime.availability.status != "available" or runtime.availability.backend_id != "mock-judge"
                    or runtime.availability.reason != "synthetic_mock_only"):
                self.fail("backend_unavailable")
                raise RunnerChannelError("runner_runtime_unavailable")
            renewal = self._broker.renew(self._lease)
            if renewal is None:
                self.close()
                raise RunnerChannelError("execution_authority_lost")
            self._started = True
            dispatch = RunnerDispatch(protocol_version=RUNNER_PROTOCOL_VERSION, identity=self._identity,
                request=self._lease.request,
                grants=tuple(self._issue(operation, renewal.expires_at)
                    for operation in ("heartbeat", "submit_result", "cancel")))
            return canonical_json(dispatch)

    def _verify(self, model, raw, observed_identity):
        self._observe(observed_identity)
        if self._closed or not self._started:
            raise RunnerChannelError("runner_channel_closed")
        message = parse_runner_message(model, raw)
        record = self._grants.get(message.grant.operation)
        if (message.identity != self._identity or message.grant.binding != self._binding or record is None
                or not compare_digest(_metadata_digest(message.grant), record.metadata_digest)
                or not compare_digest(_token_digest(message.grant.token), record.token_digest)):
            raise RunnerChannelError("runner_grant_invalid")
        return message

    def heartbeat(self, raw, *, observed_identity) -> bytes:
        with self._lock:
            message = self._verify(RunnerHeartbeat, raw, observed_identity)
            renewal = self._broker.renew(self._lease)
            if renewal is None:
                self.close()
                raise RunnerChannelError("execution_authority_lost")
            grant = self._issue("heartbeat", renewal.expires_at)
            return canonical_json(RunnerHeartbeatAck(protocol_version=RUNNER_PROTOCOL_VERSION,
                message_id=message.message_id, identity=self._identity, grant=grant,
                heartbeat_at=renewal.heartbeat_at, lease_expires_at=renewal.lease_expires_at,
                expires_at=renewal.expires_at, deadline_at=renewal.deadline_at))

    def submit_result(self, raw, *, observed_identity) -> dict:
        with self._lock:
            message = self._verify(RunnerResultSubmission, raw, observed_identity)
            # The rotating operation grant is narrower than this private Broker
            # lease. Broker.complete remains the DB-authoritative commit barrier.
            try:
                return self._broker.complete(self._lease, message.result)
            finally:
                self.close()

    def cancellation(self, raw, *, observed_identity) -> bytes:
        """Confirm persisted owner cancellation; this cannot cancel a Broker job."""
        with self._lock:
            message = self._verify(RunnerCancellation, raw, observed_identity)
            if not self._broker.cancelled(self._lease):
                raise RunnerChannelError("job_not_cancelled")
            self._cancel_message_id = message.message_id
            wire = canonical_json(message)
            self.close()
            return wire

    def acknowledge_cleanup(self, raw, *, observed_identity):
        """Accept only fixed no-resource Mock cleanup, never an OS teardown claim."""
        with self._lock:
            self._observe(observed_identity)
            ack = parse_runner_message(RunnerCancellationAck, raw)
            if (self._cancel_message_id is None or ack.message_id != self._cancel_message_id
                    or ack.identity != self._identity or ack.binding != self._binding):
                raise RunnerChannelError("runner_cleanup_invalid")
            self._cancel_message_id = None
            return ack.cleanup

    def fail(self, code="backend_error"):
        with self._lock:
            if self._closed:
                return False
            try:
                return self._broker.fail(self._lease, code)
            finally:
                self.close()

    def close(self):
        """Discard all grants/private lease; retain only bounded cleanup correlation."""
        with self._lock:
            self._grants.clear()
            self._lease = None
            self._closed = True
