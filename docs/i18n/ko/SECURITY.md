# 보안 경계

[English — canonical source](../../../SECURITY.md)

PraxiOJ M6-A는 독립 개인 오픈소스 프로젝트의 개발 미리보기다. 공개 배포는 승인되지 않았다. `PRAXIOJ_ENV`는 `development`와 `test`만 허용하며, 네이티브 서버는 루프백에 바인딩해야 한다. Compose는 API/web 포트만 루프백에 공개하며, 선택적인 네이티브 개발용 Override를 사용하지 않는 한 PostgreSQL 포트를 공개하지 않는다. API와 Worker 컨테이너는 외부 요청을 시작할 수 있고, 설정된 데이터베이스·Provider 권한을 공유한다. 컨테이너 네트워크, 프로세스 분리와 논리적 파일은 참가자 실행용 Sandbox가 아니다.

## 시스템과 신뢰 경계

Framework는 Manifest, Provider, Tool, Trace와 결정적 평가를 정의한다. Platform은 계정, Job과 참가자 데이터를 저장한다. 참가자와 모델 출력은 신뢰하지 않는다. 문제 작성자는 자신이 관리하는 문제에 한해 선언형 Manifest를 발행할 수 있다. 로컬 운영자는 Provider URL·자격증명, 역할 부여와 배포를 제어한다. 데이터베이스·호스트 관리자는 저장소 접근 권한을 가진 신뢰 주체다. 이벤트 Hash Chain은 관리자가 증거와 Checkpoint를 함께 다시 쓰는 행위를 막지 못한다.

## 구현된 제어와 불변조건

- 비밀번호는 argon2-cffi를 통해 Argon2id(64 MiB, 반복 3회, 병렬도 4)를 사용한다. 무작위 로그인·CSRF 토큰은 Hash로 저장한다. HttpOnly, SameSite=Strict Cookie에는 제한된 만료 시간이 있으며, 로컬 HTTPS용 Secure 설정을 선택할 수 있다. 로그인은 해당 계정이 제시한 현재 세션을 교체하고, 활성 로그인 수를 제한하며, 소유자는 개별 세션을 폐기할 수 있다. 비밀번호·역할 변경은 모든 로그인을 폐기한다. Export와 계정 삭제에는 동일한 로그인 세션에서 최근에 수행한 비밀번호 확인이 필요하다. 기본 관리자 비밀번호나 기존 브라우저 식별자의 자동 권한 상승은 없다.
- 회원가입·로그인에는 허용된 Origin이 필요하다. 회원가입은 자동 로그인 없이 일반적인 확인 응답을 반환하며, 로그인 실패는 계정 존재 여부를 공개하지 않는다. 인증된 변경 요청에는 Synchronizer CSRF Header가 필요하다. Cross-site 요청, 예상하지 않은 Host, JSON이 아닌 쓰기 요청과 크기 제한을 넘는 Body는 거부한다. 인증·일반 API 시도에는 원자적으로 공유되는 PostgreSQL Rate Bucket, 제한된 시간 구간과 재시도 Header가 적용된다. 지원하는 Uvicorn 명령은 Proxy Header 해석을 비활성화하며, 임의의 전달 IP Header를 신뢰하지 않는다. Proxy를 거치는 클라이언트는 보수적으로 Proxy 전송 연결의 IP 한도를 공유한다. Health Probe는 일반 요청 제한에서 제외한다.
- Backend는 administrator/author/participant 역할과 리소스 소유권을 검사한다. 다른 참가자는 세션, 대화, Run, 논리적 파일, 제출물, 평가나 Trace를 읽거나 변경할 수 없다. 작성자 검토는 소유한 문제로 한정하며 최소한의 평가 정보만 공개한다. 관리자 Audit Endpoint는 참가자 원문과 자격증명을 제외한다.
- 사용자 우선 변경 잠금은 계정 삭제와 새로운 비공개 쓰기를 직렬화한다. 세션 잠금은 Trace 순번 할당과 Workspace 변경을 직렬화한다. 변경 불가능한 문제 버전·제출물은 Content Digest를 가지며, 새 이벤트에는 Hash Chain과 저장된 Checkpoint가 있다. Legacy 이벤트는 검증되지 않은 상태임을 명시한다.
- API 트랜잭션은 요청 UUID가 있는 영속 Job을 Queue에 넣는다. Worker는 PostgreSQL 행 잠금과 SKIP LOCKED로 Job을 획득하고, Lease를 갱신하며, 결과 반영이나 Tool 변경 전에 매번 Token/Fence/만료를 검사한다. 취소는 확인 응답 전에 소유권을 폐기한다. 만료된 Job은 과금 가능성이 있는 Provider 호출을 자동으로 반복하지 않고 실패한다. 외부 실행의 Exactly-once는 보장하지 않는다.
- 계정·시스템 Admission은 활성·보존 세션, 동시 Run, 대기·실행 Job과 예약된 논리적 저장 용량을 제한한다. 사용자·문제·시스템의 UTC 일별 예산은 실행 전에 모델·Tool 시도량을 예약한다. 알 수 없거나 추정된 Provider 사용량은 명시적인 정책 예약량으로 남으며, 임의로 만든 정확한 Token 수나 보장된 청구 한도가 아니다. Trace 용량은 완료 처리에 필요한 제한된 공간을 예약하며, 과거 증거가 새로운 한도를 초과하더라도 보존한다. 이 한도는 파일시스템·데이터베이스 Volume Quota나 악성 코드의 CPU·Memory 격리를 대체하지 않는다.
- Worker 상태, Queue 깊이·대기 시간, 대기·실행 관측값과 안전한 Counter는 관리자에게만 공개한다. API 시간 로그는 원시 URL, Body나 클라이언트 IP 없이 제한된 Route 분류를 사용한다. Worker는 제한된 시간 동안 Drain한 뒤 로컬 대기를 취소하며, 데이터베이스 연결·쿼리 대기에도 한도가 있다. 독립 Maintenance는 AI Worker 없이 Lease를 조정하고 정리 대상 데이터를 Purge할 수 있다. 운영자가 구성한 Scheduler의 중단·연결 끊김은 여전히 가용성에 영향을 준다.
- Provider Endpoint·Key는 서버에서 관리한다. 참가자는 설정된 Profile과 문제에서 허용한 모델을 선택한다. HTTPX는 Proxy 설정 상속과 Redirect를 비활성화하며, 요청·응답 크기와 경과 시간을 제한한다. 기능 지원 여부는 명시한다. 이러한 제어가 신뢰하는 운영자의 임의 Endpoint 설정을 SSRF에 안전한 Sandbox로 만드는 것은 아니다.
- Tool Input에는 엄격한 Schema, 상대 경로 검증, Allowlist, 필수 권한과 파일·개수·Byte 한도가 적용된다. Store는 하나의 세션에 결합된다. Shell, 호스트 파일시스템, 범용 네트워크, 임의 코드나 비신뢰 컨테이너 Tool은 없다. 모델 출력을 권한이 높은 지시 역할로 승격하지 않는다.
- 프로세스 안에서는 코드에 포함된 신뢰할 수 있는 Evaluator만 실행한다. 작성자의 평가 기준은 제한된 데이터이며 모듈 경로나 Python 코드가 아니다. 공개 문제 정보는 비공개 설정을 제외한다. 이벤트 증거는 관측 가능한 행동을 측정하며, 숨겨진 추론이나 사람의 이해를 보장하지 않는다.
- Trace Payload 보존 기간은 최대 90일로 제한한다. 만료된 읽기·쓰기는 Fail-closed로 차단하며, Worker 또는 Maintenance CLI가 Payload를 Purge하고 최소한의 삭제 Metadata를 기록한다. 계정 삭제는 비공개 풀이 데이터를 제거하고 세션을 폐기하며, 비활성 가명 소유권·Audit Tombstone을 남긴다. Audit Record에는 별도의 최대 90일 보존 기간이 있다.
- 소유자 Export에는 CSRF와 비밀번호 확인이 필요하다. 명시적으로 안전한 공개 필드와 Page·Row·Byte 한도를 사용하며, 만료된 Trace와 자격증명을 제외한다. 삭제는 실패 시 Rollback하는 단일 트랜잭션으로 유지하며 활성 Run이 있으면 거부한다. 클라이언트가 다운로드한 파일은 서버 보존 정책 밖의 독립적인 비공개 사본이다.
- Backup Tool은 신뢰하는 운영자의 Archive만 허용한다. 저장소 밖에 소유자만 접근할 수 있는 파일을 저장하며, 데이터베이스 작업 전에 Checksum과 PostgreSQL Client/Server Identity를 확인한다. Restore는 새로운 데이터베이스를 만들고, 복원 전에 서비스·실행 Quarantine을 설치하며, Schema를 검증하고 복원된 로그인 세션을 폐기한다. 승격 명령은 없다. Checksum은 서명이 아니며 PostgreSQL Archive는 SQL을 실행할 수 있다. 이 관리 절차는 비신뢰 업로드용 Sandbox가 아니다.
- 새로 저장하는 Text는 설정된 Provider Key와 인식한 민감 필드·Token Pattern을 제거한다. 참가자 오류에서는 Provider 원시 Body, Header, URL과 내부 예외 상세를 제외한다. 내부 진단은 제어된 Code와 Operation ID를 사용한다. 검증 응답은 제출된 Input 값을 제외한다. React는 사용자·모델 Text를 Text로 렌더링한다.

## M5 Judge 기반 불변조건

- `praxioj.execution`은 크기가 제한된 UTF-8 JSON, 이식 가능한 논리적 경로, 명시적 Version, Identity/Digest 상관관계와 유한하고 제한된 평가 기준 점수를 갖는 엄격한 Version 1.0 요청·결과 Protocol을 정의한다. Metadata와 Content Hash는 고정된 Input에 대한 검증을 제공하며, 호스트 격리나 독립 실행의 진실성을 입증하지 않는다.
- 합성 Judge Harness의 기본값은 `unavailable`이다. 서버에서 명시적으로 `mock`을 설정한 경우에만 인증된 관리자가 자신이 제출한 고정 release-plan Fixture를 사용할 수 있다. 클라이언트는 명령, 소스 코드, Evaluator Module, Runtime Image나 Policy를 선택할 수 없다. 알 수 없는 Backend는 설정 단계에서 거부한다. 실행 불가 상태에서 Mock을 대체 수단으로 Dispatch하지 않는다. Mock은 Process, Shell, 파일시스템 수집, 참가자 코드 Import나 네트워크 호출을 사용하지 않는다.
- Judge Job/Attempt Record와 예약량은 AI Job·Provider 사용량과 분리한다. 불투명한 256-bit 결과 Capability는 Hash로만 저장하며, 하나의 Job/Attempt, Audience, Operation, 만료, 고정된 요청과 유효한 Lease/Fence에 결합된다. 결과 수락은 행 잠금 아래에서 현재 계정 역할, 소유권, 변경 불가능한 제출물·문제, Trace Checkpoint·만료와 Terminal/Revoked/Consumed 상태를 다시 검사한다. 취소·만료·수락된 결과는 권한을 무효화하며, 자동 재시도나 덮어쓰기는 허용하지 않는다. 잘못된 Token은 다른 유효한 Attempt를 취소할 수 없다.
- 신뢰하는 Broker는 Platform 데이터베이스 권한을 유지한다. Mock Backend는 제한된 실행 요청만 받으며 로그인·CSRF Token, Capability 평문, 애플리케이션 설정, 데이터베이스 접근 권한이나 Provider 자격증명을 받지 않는다. Backend 결과는 저장 전에 신뢰하지 않는 데이터로 검증한다. 안전한 수명주기 Audit에는 잘못된 결과 원문이나 Token 없이 제어된 ID·Code만 포함한다.
- 합성 평가는 항상 `provenance=synthetic_mock`과 `independent_execution_evidence=false`를 가진다. 별도로 저장하며, 기존 내장 Evaluation을 대체하거나 격리된 참가자 실행의 증거가 될 수 없다. Trace 만료는 활성 Judge 권한을 종료하고 예약량을 해제한다. 보존된 고정 합성 출력에는 복사한 Trace Payload가 없으며 Export는 증거 만료를 명시한다. 활성 Judge 작업이 있으면 계정 삭제를 거부하고, 이후 모든 Terminal Job/Attempt 데이터를 Cascade 삭제한다. 복원된 데이터베이스는 Judge 작업을 Enqueue·Claim·Complete할 수 없다.

## M6-A 수명주기와 합성 Runner 불변조건

- Judge 갱신은 정해진 잠금 순서 아래에서 현재 소유자·Source, Worker/Attempt/Fence, Token, 고정된 요청과 만료되지 않은 권한을 다시 검사한다. 확인 응답은 데이터베이스에서 관측한 시간을 사용하며 원래 Deadline이나 Capability 만료를 연장할 수 없다. Dispatch는 Terminal 처리 전에 갱신 Loop가 종료될 때까지 기다린다. 갱신 권한을 잃으면 로컬 Mock 대기를 취소한다. 중단된 Worker는 자동 Replay 없이 만료된다. Backend 실행에 걸쳐 데이터베이스 트랜잭션을 유지하지 않는다.
- 별도의 Version 1.0 Runner Channel은 신뢰하는 프로세스 안에서 교환하는 제한된 직렬화 데이터다. Gateway는 하나의 비공개 Broker Lease와 최대 3개의 Operation Grant Hash를 가진다. Heartbeat Grant는 갱신에 성공하면 교체하며, 결과 권한은 한 번만 사용할 수 있다. Identity는 신뢰하는 Mock Channel 생성 과정에서 얻고, 메시지 Identity 및 Request/Attempt/Fence/Input/Policy/Image 결합과 대조한다. 스스로 선언한 Identity와 Digest 보유는 원격 인증이 아니다. 공개 Runner Endpoint, 운영용 Peer 인증이나 Host Attestation은 구현하지 않았다. 고정 Backend는 여전히 실행 요청만 받으며 Gateway/Broker 자격증명, DB 접근 권한, 설정이나 Provider Secret을 받지 않는다.
- 취소 알림은 결합된 원래 Attempt의 취소가 저장되어 있음을 확인해야 한다. Runner 메시지는 임의의 Broker 작업을 취소할 수 없다. Cleanup 확인 응답은 고정된 합성 무자원 상태만 허용한다. Channel을 닫으면 Grant를 버리고, 재시작하면 일시적인 Channel 권한을 잃는다. 저장된 Attempt의 만료·복구가 계속 권한 판단의 기준이다. 이것은 호스트 Process 종료나 실제 Sandbox 용량의 안전한 재사용을 입증하지 않는다.
- Terminal Judge Payload와 Metadata의 기본 보존 기간은 각각 7일과 30일이며, 정수 범위는 `1 <= result <= metadata <= 90`이다. 독립적이고 처리량이 제한된 Maintenance는 소유자 우선 잠금 아래에서 Terminal 경과 시간과 유효한 권한의 부재를 다시 검사한다. Payload Purge는 결과·비공개 요청·Attempt Capability를 제거하고, 증거를 사용할 수 없음을 명시한 안전한 평가를 보존하며 Payload 용량을 회수한다. 요약에는 별도의 4배 보존 Row 한도가 있으며 이후 만료된다. 원래 제출물, 내장 평가 점수와 Trace는 별개다. 계정 삭제와 Restore Quarantine은 계속 적용한다. TTL 정리 대상이 된 시점이 정확한 물리적 삭제 일정을 의미하지는 않으며, 코드·Schema Rollback으로 Purge된 증거를 재생성할 수 없다. 멱등성 이력은 Job Record가 남아 있는 동안에만 유지한다.

구현된 경계와 미완료 경계는 [Judge 수명주기](architecture/judge-lifecycle.md), [Runner Protocol](specifications/runner-protocol.md), [Linux Preflight](development/linux-runner-preflight.md)를 참고한다. 이 추가 사항은 보고 대상 기준을 바꾸거나 새로운 보안 제외 사항을 수용하지 않는다.

## 보고할 문제와 한계

인증 우회, 권한 상승, 계정 간 접근, CSRF, 안전하지 않은 Tool 경로, 자원 한도 우회, 오래된 Worker의 쓰기, Judge Capability/Replay 또는 결과 결합 우회, 증거·보존 정책 불일치, 자격증명 노출과 안전하지 않은 Dependency·Build 동작은 유의미한 보고 대상이다. Localhost 제한은 애플리케이션 경계 결함을 정당화하지 않는다. 현실적인 선행 조건과 영향받는 경로를 보고하고, 테스트나 Scanner의 미탐지만으로 안전하다고 추론하지 않는다.

공개 배포는 계속 지원하지 않는다. MFA, 비밀번호 Reset/Recovery, 검증된 Identity, 운영용 TLS/Proxy 설정, 포괄적인 분산 악용 모니터링, 저장 데이터 암호화와 Secret Vault는 구현하지 않았다. 애플리케이션 Admission과 로컬 Metric은 완전한 악용 방어나 운영 체계를 구성하지 않는다. 모든 Worker가 중단되면 물리적 Cleanup과 Lease 조정에는 독립적으로 예약한 Maintenance 명령이 필요하다. 만료된 Trace 읽기는 계속 차단한다. 애플리케이션은 Backup Archive를 암호화하지 않으므로 운영자가 관리하는 암호화 저장소가 필요하다. 현재 데이터 삭제는 과거 Backup이나 브라우저 다운로드를 삭제하지 않는다. 외부 삭제 원장 복제, 자동 Backup/Key 수명주기와 검토된 복구 승격은 미구현이며, 복원된 데이터베이스는 계속 차단한다. 인식하지 못한 PII·Secret은 대화나 과거 Record에 남을 수 있다. 이 미리보기에서 민감한 실제 참가자 데이터를 사용하지 않는다.

안전한 비신뢰 코드 Sandbox, 외부 Evaluator Runner나 분산 Judge는 없다. 분리된 AI Worker는 신뢰하는 Runtime/Tool 코드만 실행한다. 완전히 변조 불가능한 증거나 재현 가능한 외부 LLM Replay는 주장하지 않는다. 네이티브 Windows Build 경로 동작과 실제 상용 LLM 추론은 별도 검증이 필요하다.

[Sandbox 위협 모델](../../architecture/sandbox-threat-model.md)과 [격리 제안](../../architecture/sandbox-architecture.md)은 향후 신뢰 경계와 수용 Gate를 정의한다. 이 문서는 실행 격리를 활성화하거나 인증하지 않는다.

## 제보

GitHub Private Vulnerability Reporting을 활성화했다. [Report a vulnerability](https://github.com/casing1/praxioj/security/advisories/new)로 유지관리자에게 비공개로 연락한다. 영향받는 Version, 선행 조건, 영향과 최소한의 합성 재현 절차를 포함한다. 실제 자격증명, 참가자 데이터나 비공개 제출물은 포함하지 않는다. 검토 중에는 민감한 상세를 공개 Issue나 PR에 게시하지 않는다. Apache-2.0 소스 공개는 공개 서비스 배포를 승인하지 않는다.
