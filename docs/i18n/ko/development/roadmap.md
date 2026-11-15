# 로드맵

[English — canonical source](../../../development/roadmap.md)

## 완료된 기반

M1은 독립적인 Problem SDK, Runtime/Mock 계약, Trace/Evaluation 인터페이스, PostgreSQL API와 초기 Sample을 제공한다. M2는 OpenAI-compatible Provider, 제한된 논리적 Tool, 영속 대화·Draft, 사용량, 취소와 Workspace UI를 추가한다. 이 단계의 Manifest Digest와 핵심 회귀 시나리오는 계속 지원한다.

M3는 Argon2id 계정과 서버 세션, CSRF와 Backend 역할, 변경 불가능한 작성자 발행, PostgreSQL Job Repository와 별도 Worker, 소유권 Lease/Fencing, Trace 무결성·보존과 결정적 증거 평가 기준을 추가한다. 자격증명 없이 Mock과 로컬 Fixture를 사용하는 테스트를 유지한다. 실제 검사와 남은 한계는 영문 [M3 검증](../../../development/validation-m3.md)과 [GitHub Preflight 보고서](../../../development/preflight-validation.md)를 참고한다.

## Milestone 4 운영 기반

M4는 공유 인증·API 요청 제한, 세션·비밀번호 관리, 확인 절차로 보호하는 Export·삭제, 계정·문제·시스템 Quota, 제한된 Trace·Artifact 용량, Worker Registry·Metric·Graceful Drain, 독립 Maintenance와 합성 PostgreSQL Backup/Restore 검증을 구현한다. 복원된 데이터베이스의 API·Worker 사용은 차단한다. 임의 코드 실행을 활성화하지 않고 향후 격리 실행 아키텍처를 문서화한다. 영문 [M4 검증·최적화 근거](../../../development/validation-m4.md)를 참고한다.

## Milestone 5 실행 기반

M5는 엄격한 버전별 실행 계약, 별도의 영속 Job/Attempt 상태를 갖는 명시적 선택 방식의 합성 Execution Broker, 불투명 Capability 검증, Lease/Fencing/Replay 보호, 제한된 Result/Artifact 검증과 합성 평가 연결을 구현한다. 기본 Backend는 계속 실행 불가 상태다. 관리자가 소유한 고정 Fixture로 코드 실행을 활성화하거나 원래 평가 점수를 바꾸지 않고 전체 로컬 HTTP 경로를 검증한다. 영문 [M5 검증](../../../development/validation-m5.md), [Execution Protocol](../../../specifications/execution-protocol.md), [Broker 아키텍처](../../../architecture/execution-broker.md)를 참고한다.

## M6-A — 수명주기와 원격 Runner 기반

[M6-A Milestone 1](https://github.com/casing1/praxioj/milestone/1)은 Issue 우선 개발 관리, DB 확인 응답에 따른 Heartbeat/Fencing, 제한된 Terminal Judge 보존·Quota 회수, 엄격한 합성 Runner 통신 경계와 실행하지 않는 Linux Preflight를 추적한다. 기능 개발 전에 [Governance PR #28](https://github.com/casing1/praxioj/pull/28)을 병합했다. 로컬 구현·검증은 [M6-A 검증](validation-m6a.md)에 기록한다. 보호 규칙에 따른 기능 전달과 최종 보안·문서 수용 검토는 실제 Issue와 필수 검사 결과를 확인할 때까지 진행 중이다. 추적 객체 생성은 완료를 의미하지 않는다.

Judge는 기본적으로 실행 불가 상태를 유지한다. 명시적으로 선택한 Mock은 관리자 소유의 고정 Fixture와 합성 Provenance를 유지한다. Runner Channel은 메모리 내 Protocol 테스트이며, 공개 Endpoint, 운영용 Peer 인증이나 악성 코드 실행을 제공하지 않는다. 수명주기와 Runner는 하나의 권위 있는 갱신·취소 계약을 공유하므로 함께 전달한다. 최종 Milestone 검증·문서는 별도 PR로 전달한다. 새로운 주요 개발 단계는 [개발 절차](engineering-workflow.md)에 따라 실제 GitHub Milestone/Issue를 사용한다.

## M6-B와 이후 선행 조건

[M6-B — Isolated Linux Runner Validation](https://github.com/casing1/praxioj/milestone/2)과 계획 [Issues #23–#27](https://github.com/casing1/praxioj/issues/23)은 열린 상태로 유지한다. 이 단계의 OS 격리 수용 기준은 구현하지 않았으며, M6-A 합성 테스트로 입증되지도 않았다. [Linux Preflight](linux-runner-preflight.md)는 실측한 호스트 사실과 확인하지 못한 요구사항을 구분한다.

1. 악성 코드 Runner를 구현하기 전에 전용 폐기 가능 Linux 실행 호스트/VM을 준비하고 지원하는 Kernel/KVM 환경을 선택한다. KVM을 사용할 수 있으면 Firecracker를 우선 검토하며, gVisor는 독립적으로 검증할 대안으로 평가한다. Runtime/Image Provenance, 권한 범위, 자원 Overhead와 언어 호환성을 기록하고 지원하지 않는 호스트에서는 Fail-closed로 거부한다. 영문 [격리 제안](../../../architecture/sandbox-architecture.md)을 참고한다.
2. M6-A의 메모리 내 Channel을 다른 호스트로 확장하기 전에 실제 인증된 원격 Transport와 Identity Provisioning을 선택·검증한다. 미완료 Host/Network/Filesystem/Process/Cleanup 수용 Gate를 충족한다. 버전별 합성 Protocol 테스트는 OS 격리나 운영용 네트워크 인증을 입증하지 않는다.
3. 공개 Hosting 전에 배포 중심 보안 검토를 수행한다. 검증된 TLS/Proxy 신뢰, 다중 Node 부하·악용 테스트, Identity Recovery/MFA, 사고 대응과 Secret 관리가 필요하다. 기존의 제한된 Localhost 제어는 운영 준비 인증이 아니다.
4. Worker 운영을 확장한다. 배포 Migration을 분리하고, 독립 Maintenance를 예약하며, 규모상 필요하다면 구조화된 Metric을 중앙 수집하고, 지속 부하·DB Failover·복구를 검증한다. 불확실한 Provider 결과를 사용자에게 드러나지 않는 자동 재시도로 숨기지 않고 명시적으로 유지한다.
5. 데이터 관리를 발전시킨다. Key 복구를 검증한 암호화된 외부 호스트 Backup, 영속적인 외부 삭제 원장 복제와 검토된 Restore 승격, Backup 수명주기 자동화, Audit 가능한 작성자 검토 UX와 필요성이 입증된 경우 증거의 외부 앵커링을 포함한다. 현재 Restore Quarantine은 의도적으로 승격을 차단한다.
6. 작성자 평가 계약은 관측 가능하고 검증된 증거만으로 확장한다. 외부 Python Evaluator나 참가자 코드를 허용하기 전에 별도로 격리된 실행 경계를 구축한다. 현재 Worker와 컨테이너는 이 격리를 제공하지 않는다.
7. 명시적으로 선택하는 실제 Provider/모델 적합성 검증, 사용량 대사와 가격 Version 처리를 추가한다. Fixture 성공은 Protocol 동작을 입증하며 모델 품질, 모든 Provider의 호환성이나 정확한 청구를 입증하지 않는다. Streaming은 구체적인 사용성 요구가 생긴 뒤 검토할 수 있다.

대회, 결제, Leaderboard, 범용 브라우저 자동화, 무제한 Terminal 접근과 분산 비신뢰 Judge Worker는 별도의 후속 범위로 남긴다. PraxiOJ는 Apache-2.0을 사용하는 독립 취미 프로젝트이며, 기여자·제3자의 권리는 유지한다.
