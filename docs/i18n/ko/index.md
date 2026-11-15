# 문서 목차

[English](../../README.md) · [프로젝트 README](README.md)

현재 구현과 유지되는 설계 기록의 목차다. 영어가 원본이며 [번역 목록](../../translations.json)에 등록한 한국어 대응 문서를 관리한다. 아직 번역하지 않은 과거 문서는 영어 자료로 연결한다. 문서를 추가하거나 실질적으로 변경하기 전에 [문서 정책](development/documentation-policy.md)을 따른다.

## 시작하기

- [로컬 설정과 지원 명령](../../development/local-setup.md) (영문)
- [AI Workspace와 자격증명 없는 Provider Fixture](../../development/ai-workspace.md) (영문)
- [기여 안내](CONTRIBUTING.md)와 [개발 절차](development/engineering-workflow.md)
- [구현 상태와 계획을 구분하는 로드맵](development/roadmap.md)
- [변경 이력](../../../CHANGELOG.md)과 [라이선스·배포 안내](../../development/licensing.md) (영문)

## 아키텍처

다음 기존 기술 문서는 영문이다.

- [전체 구조](../../architecture/overview.md)와 [모듈 경계](../../architecture/module-boundaries.md)
- [AI 작업 영속성과 Worker 수명주기](../../architecture/persistent-jobs.md)
- [자원 할당량](../../architecture/resource-quotas.md)과 [Trace 보존](../../architecture/trace-retention.md)
- [Execution Broker](../../architecture/execution-broker.md)
- [Judge 수명주기와 증거 보존](architecture/judge-lifecycle.md)
- [실행 기반과 향후 격리 설계](../../architecture/sandbox-architecture.md)
- 과거 [M1 구현 계약](../../architecture/implementation-contract.md)과 [M2 구현 계약](../../architecture/milestone-2-contract.md)

## 명세

다음 기존 명세는 영문이다.

- [문제 패키지 형식](../../specifications/problem-format.md)
- [Runtime, Tool, 자원 집계](../../specifications/runtime-and-tools.md)
- [Trace 이벤트와 무결성](../../specifications/trace-events.md)
- [평가 계약](../../specifications/evaluation-contract.md)
- [실행 프로토콜, Capability, 결과 검증](../../specifications/execution-protocol.md)
- [합성 Runner 채널과 인증 경계](specifications/runner-protocol.md)

## 개발과 관리

- [개발 절차](development/engineering-workflow.md)
- [문서·번역 정책](development/documentation-policy.md)
- [AuthZest 참고 분석과 PraxiOJ 적용 결정](development/governance-reference.md)
- [개발 관리 기반 검증](development/validation-governance.md)
- [의존성과 환경 버전](../../development/versions.md) (영문)
- [로드맵](development/roadmap.md)
- [Linux Runner 사전 점검과 미완료 M6-B 호스트 수용 조건](development/linux-runner-preflight.md)

## 운영·보안 안내

다음 기존 안내는 영문이다.

- [보안 정책과 비공개 제보](SECURITY.md)
- [실행 격리 위협 모델](../../architecture/sandbox-threat-model.md)
- [인증·인가](../../development/authentication.md)
- [계정 내보내기와 삭제](../../development/data-governance.md)
- [로컬 백업·복구 검증·격리](../../development/backup-restore.md)

Platform은 localhost 개발 미리보기다. 프로토콜 검사, Mock 테스트, Docker Compose는 운영체제 수준의 보안 Sandbox나 공개 배포 적합성을 입증하지 않는다.

## 검증 기록

- [M6-A 수명주기·Runner 검증](development/validation-m6a.md)

다음 과거 검증 보고서는 영문이다.

- [M5 실행 기반](../../development/validation-m5.md)
- [M4 운영 제어](../../development/validation-m4.md)
- [M3 Platform 기반](../../development/validation-m3.md)
- [GitHub 공개 준비 보완](../../development/preflight-validation.md)
- [M2 AI Workspace](../../development/validation-m2.md)
- [M1 초기 기반](../../development/validation.md)

각 보고서의 결과는 해당 리비전·환경·검증 범위에 한정된다. 과거 통과 수를 현재 테스트 결과로 취급하지 않는다. M6-A 보고서는 현재 로컬 검증과 진행 중인 보호된 전달·최종 수용 단계를 구분한다.

## 문서 템플릿

- [아키텍처·설계](templates/design.md)
- [기술 명세](templates/specification.md)
- [검증 보고서](templates/validation.md)
- [보안 검토](templates/security-review.md)

템플릿은 작성 지침이며 완료된 증거가 아니다. 해당하지 않는 절은 삭제하거나 적용되지 않는 이유를 쓰고, 완성 문서를 게시하기 전에 모든 작성 지침을 실제 내용으로 바꾼다.
