# Synthetic Runner communication protocol

[한국어](../i18n/ko/specifications/runner-protocol.md) · [Documentation index](../README.md)

## Overview, scope and status

M6-A provides versioned Runner messages and a verifiable in-memory channel for a single fixed Mock attempt. [Issue #19](https://github.com/casing1/praxioj/issues/19) tracks the contract and authentication boundary; [#21](https://github.com/casing1/praxioj/issues/21) tracks security tests. This is implemented foundation code, not a deployed remote Runner. Final validation/delivery is recorded in [M6-A validation](../development/validation-m6a.md).

The selected transport is `in_memory_mock`: serialized bytes cross a narrow interface, while the trusted Platform retains SQL/account authority and the original Broker lease. No HTTP listener, socket client, runner provisioning, arbitrary URL/command, code execution or production authentication is added. M6-B must select and independently validate an authenticated channel and actual isolated host before enabling another transport. A message's claimed identity is not proof of its sender.

## Components and trust boundary

| Component | Responsibility and authority |
| --- | --- |
| `praxioj.execution.runner` | Framework-only immutable models, fresh bounded parsing and fixed `MockRunnerTransport`; no FastAPI, ORM or Platform imports |
| `JudgeRunnerGateway` | Trusted Platform adapter for one existing `JudgeLease`; current DB authority remains in `JudgeBroker` |
| `MockRunnerTransport` | One active synthetic attempt, observed identity, bounded wire messages, fixed Mock result generation and logical cancellation |
| `MockJudgeBackend` | Receives only `ExecutionRequest`; it never receives the channel grants, Broker token, database, settings, cookie/CSRF or LLM credentials |

The gateway holds one private Broker lease and a maximum of three active grant hashes. Its per-instance lock serializes local grant rotation/result consumption; it does not replace PostgreSQL authorization. Transport identity is obtained from a **trusted constructor** and supplied separately as `observed_identity`. Reading that value from the untrusted message would violate this boundary. In-process Python objects are not malicious-code confinement.

## Terminology and data model

- Protocol version is explicitly `"1.0"`, independent of the unchanged M5 execution request/result version `"1.0"`.
- `RunnerIdentity`: bounded `runner_id`, `transport="in_memory_mock"`, `synthetic_only=true`, `host_isolation_verified=false`. It declares the narrow supported test mode; it is not a certificate or attestation.
- `RunnerBinding`: request/job/attempt UUIDs, positive fence, full request digest, input digest, policy digest and runtime-image digest. The full request digest also binds the session, submission, evaluator, criteria, limits and deadline in the M5 request. Platform ownership is independently checked by the Broker.
- `RunnerGrant`: unique grant UUID, 256-bit opaque URL-safe token, audience, one operation, exact binding and fixed capability expiry. Tokens are omitted from representations. Wire serialization intentionally carries a grant only to its bound Mock channel; never log those bytes.
- Supported operations are exactly `heartbeat`, `submit_result` and `cancel`. Dispatch supplies three distinct IDs/tokens with distinct operations. A grant cannot be substituted across operations or attempts.

The gateway stores SHA-256 token hashes and a digest of authoritative grant metadata, not plaintext channel tokens. Tampering with expiry, identity, operation or any binding changes metadata validation. Constant-time token comparison alone is insufficient: every authorized mutation still passes the Broker's current lease/fence/source/expiry checks.

## Interfaces and protocol

All wire interfaces accept/return UTF-8 JSON bytes or supported parsed values through `parse_runner_message()`. Fresh parsing applies extra-field rejection, explicit versions, finite/strict values, duplicate-key detection, depth/node limits and a **64 KiB total envelope** cap. The cap includes grants and routing metadata, so it can be stricter than the inner M5 result budget; an oversized legal inner result is rejected rather than exempted. No compressed body, archive, executable content loader or implicit fallback is introduced.

| Message | Validation and effect |
| --- | --- |
| `RunnerRuntimeStatus` | Identity and declared availability; gateway accepts only the fixed available `mock-judge` / `synthetic_mock_only` mode |
| `RunnerDispatch` | Immutable M5 request and exactly three distinct bound grants; no source, policy or runtime override |
| `RunnerHeartbeat` | One current heartbeat grant and message UUID; successful DB renewal rotates that grant |
| `RunnerHeartbeatAck` | Correlated UUID, observed identity, fresh heartbeat grant and DB-observed heartbeat/lease/capability/deadline times |
| `RunnerResultSubmission` | One result grant and untrusted bounded result object; `Broker.complete()` performs all M5 schema/artifact/score/source validation before commit |
| `RunnerCancellation` | Bound stop poll/notification; gateway confirms the original attempt's persisted owner cancellation before emitting it |
| `RunnerCancellationAck` | Exact notification UUID/identity/binding and fixed `not_required/synthetic_no_resources` cleanup; never proof of guest teardown |

Gateway calls are `start()`, `heartbeat()`, `submit_result()`, `cancellation()`, `acknowledge_cleanup()`, `fail()` and `close()`. Transport calls are `availability()`, `open()`, `heartbeat()`, `acknowledge()`, async `execute()`, `cancellation_poll()`, `cancel()` and `close()`. There is no general result-upload endpoint or credential vending API.

## Preconditions and transitions

1. A trusted caller admits an eligible administrator-owned fixed fixture and claims it with a worker ID matching the trusted transport identity.
2. The gateway validates observed and declared identity/availability, then asks the Broker for current DB renewal before issuing a dispatch. A missing or unavailable runtime never selects a host fallback.
3. Transport opens exactly one dispatch. A heartbeat must receive its correlated acknowledgement before another is issued. Gateway renewal consumes the old heartbeat grant by replacing its hash; replay fails. Ack times describe the server's observation and are not Runner clock authority.
4. The fixed backend produces a bounded synthetic result. The gateway first validates channel identity/grant/binding; invalid channel messages leave genuine authority available. After that validation, Broker result submission is attempted once and the gateway closes even on Broker rejection or ambiguous failure. There is no transparent retry or resurrection.
5. Owner cancellation is a separate authenticated Broker action. Runner polling cannot cancel Broker state. Only confirmed cancellation of that bound original attempt produces the logical stop message; wrong, stale or expired authority is rejected.
6. Cleanup acknowledgement consumes its single pending correlation. `close()` is idempotent and drops grants/private lease; transport closure drops channel data. An in-flight Mock delivery cannot be reopened as another attempt.

The existing HTTP synthetic dispatcher independently runs the [lifecycle heartbeat loop](../architecture/judge-lifecycle.md). The Runner foundation is exercised through its explicit trusted gateway/Mock transport integration; it is not silently enabled as a network service or a separate Judge scheduler.

## Security invariants and errors

- Validate separately observed identity, current grant metadata/hash, operation, request/attempt/fence/digests and authoritative Broker state before a mutation.
- Do not use caller timestamps, a self-declared runner ID, an echoed nonce or a digest as authentication or lease extension.
- Wrong identity/token/binding does not consume or cancel legitimate Broker work. Accepted heartbeat replay, result replay, post-cancel renewal and old-worker results fail closed.
- Original Broker tokens, DB/provider credentials and account sessions never cross the Runner wire. Results and cleanup claims are untrusted data, not privileged instructions, SQL, code or score authority.
- Gateway state is deliberately transient. Restart or closure loses channel authority; a durable job may remain running until lease/deadline recovery, without automatic replay. No restart-resumable grant store or production identity provisioning is claimed.
- Parsing/channel errors use controlled codes; do not log raw wire messages, model validation inputs or token-bearing dumps. Unknown versions/runtime/policy and oversized/malformed content reject without fallback.

Cancellation acknowledgements only describe fixed synthetic no-resource cleanup. CPU/memory/PID/filesystem/network isolation, actual process killing and host capacity reclamation remain unverified M6-B obligations. Default backend selection stays unavailable, including when the Foundation classes are importable.

## Compatibility and test requirements

The Framework adds no dependency and remains independently installable. M5 request/result contracts, unavailable behavior, original evaluations and the boolean heartbeat facade remain supported. Migration/retention applies only to the Platform lifecycle, not these pure wire models.

Tests must cover complete serialized dispatch/heartbeat/result flow, wrong observed and payload identity, token/operation/expiry metadata tampering, replay, unknown versions, fresh validation of unsafe model copies, duplicate/nonfinite/oversized JSON, policy/input/request digest changes, actual DB expiry/cancellation, malformed results, fixed cleanup claims, close/restart failure, credential exclusion and default unavailable behavior. PostgreSQL races and failure recovery are separately measured; tests with fake/in-memory peers cannot establish network authentication or OS acceptance.

Reviewed; no unmeasured performance gain is claimed. The one-attempt/three-grant bound avoids a global registry; strict parsing and current DB checks remain intentional work. Serialization/query/lock costs and any justified optimization belong in the dedicated validation report.

## References

- [Execution protocol](execution-protocol.md), [Judge lifecycle](../architecture/judge-lifecycle.md)
- [Security policy](../../SECURITY.md), [Linux preflight](../development/linux-runner-preflight.md)
- [M6-A](https://github.com/casing1/praxioj/milestone/1), [open M6-B](https://github.com/casing1/praxioj/milestone/2)
