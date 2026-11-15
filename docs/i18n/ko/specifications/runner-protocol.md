# 합성 Runner 통신 프로토콜

[English](../../../specifications/runner-protocol.md) · [문서 목차](../index.md)

## 개요·범위·상태

M6-A는 고정된 Mock Attempt 하나에 대해 버전 관리 Runner Message와 검증 가능한 메모리 내 채널을 제공한다. [Issue #19](https://github.com/casing1/praxioj/issues/19)는 계약·인증 경계, [#21](https://github.com/casing1/praxioj/issues/21)은 보안 시험을 추적한다. 구현된 기반 코드이며 배포된 원격 Runner는 아니다. 최종 검증·전달 결과는 [M6-A 검증](../development/validation-m6a.md)에 기록한다.

선택한 Transport는 `in_memory_mock`이다. 직렬화한 Byte가 제한 인터페이스를 통과하고 신뢰하는 Platform은 SQL·계정 권한과 원래 Broker Lease를 유지한다. HTTP Listener·Socket Client·Runner 생성·임의 URL·명령·코드 실행·운영용 인증을 추가하지 않는다. 다른 Transport를 활성화하기 전에 M6-B에서 인증 채널과 실제 격리 Host를 선정하고 독립 검증해야 한다. Message가 주장하는 Identity는 송신자의 증명이 아니다.

## 컴포넌트·신뢰 경계

| 컴포넌트 | 책임·권한 |
| --- | --- |
| `praxioj.execution.runner` | Framework 전용 불변 Model·제한된 재검증·고정 `MockRunnerTransport`. FastAPI·ORM·Platform Import 없음 |
| `JudgeRunnerGateway` | 기존 `JudgeLease` 하나를 위한 신뢰하는 Platform Adapter. 현재 DB 권한은 `JudgeBroker`에 유지 |
| `MockRunnerTransport` | 활성 합성 Attempt 하나, 관찰한 Identity, 제한 Wire Message, 고정 Mock 결과 생성·논리 취소 |
| `MockJudgeBackend` | `ExecutionRequest`만 받음. Channel Grant·Broker Token·DB·Settings·Cookie/CSRF·LLM 자격증명을 받지 않음 |

Gateway는 비공개 Broker Lease 하나와 최대 3개의 활성 Grant Hash를 보유한다. Instance별 Lock이 로컬 Grant 교체·Result 소비를 직렬화하지만 PostgreSQL 인가를 대신하지 않는다. Transport Identity는 **신뢰하는 Constructor**에서 얻어 `observed_identity`로 별도 전달한다. 신뢰할 수 없는 Message에서 이 값을 읽으면 경계를 위반한다. Process 안의 Python 객체 분리는 악성 코드 격리가 아니다.

## 용어·데이터 모델

- 프로토콜 버전은 명시적인 `"1.0"`이며 기존 M5 실행 Request·Result 버전 `"1.0"`과 별도로 관리한다.
- `RunnerIdentity`: 제한된 `runner_id`, `transport="in_memory_mock"`, `synthetic_only=true`, `host_isolation_verified=false`. 지원하는 제한 테스트 모드를 선언하며 인증서·Attestation은 아니다.
- `RunnerBinding`: Request·Job·Attempt UUID, 양의 Fence, 전체 Request Digest·Input Digest·Policy Digest·Runtime Image Digest. 전체 Request Digest는 M5 요청의 Session·Submission·Evaluator·Criteria·Limit·Deadline도 결합한다. Platform 소유권은 Broker가 별도로 검사한다.
- `RunnerGrant`: 고유 Grant UUID, 256-bit 불투명 URL-safe Token, Audience, 단일 Operation, 정확한 Binding과 고정 Capability 만료. Token은 객체 표현에서 제외한다. Wire 직렬화는 결합된 Mock 채널에만 Grant를 의도적으로 전달하므로 해당 Byte를 로그에 남기지 않는다.
- 지원 Operation은 정확히 `heartbeat`, `submit_result`, `cancel`이다. Dispatch는 Operation별로 다른 ID·Token 3개를 제공하며 Operation·Attempt 사이에서 대체할 수 없다.

Gateway는 Channel Token 원문 대신 SHA-256 Token Hash와 권위 있는 Grant Metadata의 Digest를 저장한다. 만료·Identity·Operation·Binding을 변경하면 Metadata 검증이 실패한다. 상수 시간 Token 비교만으로 충분하지 않으며 인가된 변경은 Broker의 현재 Lease·Fence·Source·만료 검사도 통과해야 한다.

## 인터페이스·프로토콜

Wire 인터페이스는 `parse_runner_message()`를 통해 UTF-8 JSON Byte 또는 지원하는 파싱 값을 처리한다. 새로 파싱하면서 추가 필드 거부, 명시적 버전, 유한·엄격한 값, 중복 Key 감지, 깊이·Node 제한과 **전체 Envelope 64 KiB** 상한을 적용한다. Grant·Routing Metadata도 상한에 포함하므로 내부 M5 Result 예산보다 더 엄격할 수 있다. 내부 Result가 자체 제한을 만족해도 외부 Envelope를 초과하면 예외 없이 거부한다. 압축 Body·Archive·실행 Content Loader·암묵적 Fallback을 추가하지 않는다.

| Message | 검증·효과 |
| --- | --- |
| `RunnerRuntimeStatus` | Identity·선언한 가용성. Gateway는 고정된 Available `mock-judge` / `synthetic_mock_only` 모드만 허용 |
| `RunnerDispatch` | 불변 M5 Request와 정확히 3개의 서로 다른 결합 Grant. Source·Policy·Runtime Override 없음 |
| `RunnerHeartbeat` | 현재 Heartbeat Grant 하나와 Message UUID. DB 갱신 성공 시 Grant 교체 |
| `RunnerHeartbeatAck` | 대응 UUID·관찰 Identity·새 Heartbeat Grant와 DB가 관찰한 Heartbeat·Lease·Capability·Deadline 시각 |
| `RunnerResultSubmission` | Result Grant 하나와 신뢰할 수 없는 제한 Result 객체. `Broker.complete()`가 Commit 전에 M5 Schema·Artifact·Score·Source 검증 수행 |
| `RunnerCancellation` | 결합된 Stop Poll·Notification. Gateway가 원래 Attempt의 영속 소유자 취소를 확인한 뒤 발행 |
| `RunnerCancellationAck` | 정확한 Notification UUID·Identity·Binding과 고정 `not_required/synthetic_no_resources` Cleanup. Guest 종료 증거가 아님 |

Gateway 호출은 `start()`, `heartbeat()`, `submit_result()`, `cancellation()`, `acknowledge_cleanup()`, `fail()`, `close()`다. Transport 호출은 `availability()`, `open()`, `heartbeat()`, `acknowledge()`, 비동기 `execute()`, `cancellation_poll()`, `cancel()`, `close()`다. 일반 결과 Upload Endpoint나 자격증명 발급 API는 없다.

## 사전 조건·전이

1. 신뢰하는 호출자가 허용 조건을 충족한 관리자 소유 고정 Fixture를 Admission하고 신뢰하는 Transport Identity와 일치한 Worker ID로 Claim한다.
2. Gateway는 관찰 Identity·선언 Identity·가용성을 확인한 뒤 Broker의 현재 DB 갱신을 거쳐 Dispatch를 발행한다. Runtime이 없거나 Unavailable이어도 Host Fallback을 선택하지 않는다.
3. Transport는 Dispatch 하나만 연다. 다음 Heartbeat를 보내기 전에 대응 확인 응답을 받아야 한다. Gateway 갱신은 Hash를 교체해 이전 Heartbeat Grant를 소비하며 Replay를 거부한다. Ack 시각은 서버 관찰이며 Runner Clock 권한이 아니다.
4. 고정 Backend가 제한 합성 Result를 생성한다. Gateway는 Identity·Grant·Binding을 검사하고 최종 수용을 Broker에 위임한다. Channel 검증을 통과한 Result의 Broker 제출은 한 번 시도하며 Broker 거부·불확실한 실패에도 Gateway를 닫는다. 잘못된 Channel Identity·Token·형식은 유효한 채널을 소비하지 않는다. 투명한 재시도·작업 부활은 없다.
5. 소유자 취소는 별도로 인증된 Broker 동작이다. Runner Polling으로 Broker 상태를 취소하지 못한다. 결합된 원래 Attempt의 확인된 취소만 논리 Stop Message를 생성하며 잘못되거나 오래되거나 만료된 권한은 거부한다.
6. Cleanup 확인은 단일 대기 중인 상관관계를 소비한다. `close()`는 멱등이며 Grant·비공개 Lease를 버리고, Transport 종료는 Channel Data를 버린다. 실행 중인 Mock Delivery를 다른 Attempt로 다시 열 수 없다.

기존 HTTP 합성 Dispatcher는 [수명주기 Heartbeat Loop](../architecture/judge-lifecycle.md)를 별도로 실행한다. Runner 기반은 명시적인 신뢰 Gateway·Mock Transport 통합으로 검증하며 Network Service나 별도 Judge Scheduler로 자동 활성화되지 않는다.

## 보안 불변식·오류

- 변경 전에 별도로 관찰한 Identity, 현재 Grant Metadata·Hash, Operation, Request·Attempt·Fence·Digest와 권위 있는 Broker 상태를 검증한다.
- 호출자 Timestamp·자기 선언 Runner ID·반환받은 Nonce·Digest를 인증이나 Lease 연장의 근거로 사용하지 않는다.
- 잘못된 Identity·Token·Binding은 정상 Broker 작업을 소비·취소하지 않는다. 수용한 Heartbeat Replay·Result Replay·취소 후 갱신·오래된 Worker Result는 안전하게 거부한다.
- 원래 Broker Token·DB/Provider 자격증명·계정 Session은 Runner Wire를 통과하지 않는다. Result·Cleanup 주장은 신뢰할 수 없는 데이터이며 특권 명령·SQL·코드·Score 권한이 아니다.
- Gateway 상태는 의도적으로 일시적이다. Restart·Close로 Channel 권한을 잃으면 영속 Job은 Lease·Deadline 복구까지 Running으로 남을 수 있으며 자동 Replay하지 않는다. 재시작 후 복원 가능한 Grant Store나 운영 신원 발급을 제공한다고 주장하지 않는다.
- 파싱·Channel 오류는 통제된 Code를 사용한다. 원본 Wire Message·Model 검증 입력·Token을 포함한 Dump를 로그에 남기지 않는다. 알 수 없는 버전·Runtime·Policy와 초과·잘못된 Content는 Fallback 없이 거부한다.

Cancellation Ack는 고정된 합성 무자원 Cleanup만 설명한다. CPU·Memory·PID·Filesystem·Network 격리, 실제 Process 종료와 Host 용량 반환은 M6-B의 미검증 의무다. Foundation Class를 Import할 수 있어도 기본 Backend 선택은 Unavailable로 유지한다.

## 호환성·테스트 요구사항

Framework는 새 의존성이 없고 독립 설치를 유지한다. M5 Request·Result 계약, Unavailable 동작, 원래 Evaluation과 Boolean Heartbeat 호환 인터페이스를 유지한다. Migration·보존은 Platform 수명주기에만 적용하며 순수 Wire Model에는 적용하지 않는다.

테스트는 전체 직렬화 Dispatch·Heartbeat·Result 흐름, 관찰·Payload Identity 불일치, Token·Operation·Expiry Metadata 변조, Replay, 미지원 버전, 안전하지 않은 Model Copy 재검증, 중복·비유한·초과 JSON, Policy·Input·Request Digest 변경, 실제 DB 만료·취소, 잘못된 Result, 고정 Cleanup 주장, Close·Restart 실패, 자격증명 배제와 기본 Unavailable 동작을 포함해야 한다. PostgreSQL 경쟁·장애 복구는 별도로 측정한다. 가짜·메모리 내 Peer 테스트는 Network 인증이나 OS 수용을 입증하지 못한다.

Reviewed이며 측정하지 않은 성능 개선을 주장하지 않는다. 단일 Attempt·3개 Grant 제한으로 Global Registry를 피하지만 엄격한 파싱·현재 DB 검사는 필요한 작업이다. 직렬화·Query·Lock 비용과 정당한 최적화는 별도 검증 보고서에 기록한다.

## 참고

- [실행 프로토콜](../../../specifications/execution-protocol.md), [Judge 수명주기](../architecture/judge-lifecycle.md)
- [보안 정책](../../../../SECURITY.md), [Linux 사전 점검](../development/linux-runner-preflight.md)
- [M6-A](https://github.com/casing1/praxioj/milestone/1), [Open M6-B](https://github.com/casing1/praxioj/milestone/2)
