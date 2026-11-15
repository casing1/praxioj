# 개발 절차

[English — canonical source](../../../development/engineering-workflow.md)

이 문서는 PraxiOJ 기여자와 코딩 에이전트가 지속적으로 사용하는 개발 절차입니다. 루트 [AGENTS.md](../../../../AGENTS.md)는 Codex가 이 절차를 따르도록 지정합니다. 개발 정책은 운영 배포 적합성을 입증하는 자료가 아닙니다.

## Issue 기반 추적

M6와 이후 모든 개발 단계는 **Milestone → Issue → Feature Branch → PR → Validation → Squash Merge** 순서로 진행합니다. 시작 전에 최신 `main`, Git 상태, 열린 PR, 관련 보안 Alert와 기존 관리 객체를 확인합니다. 관계없는 변경과 사용자 데이터를 보존하고 같은 목적의 Milestone, Issue와 Label을 중복 생성하지 않습니다.

주요 단계는 실제 GitHub Milestone으로 생성하며 `M6-A — …`, `M6-B — …`, 이후 `M7 — …`, `M8 — …` 형식을 사용합니다. 설명에는 Objective, Scope, Deliverables, Acceptance Criteria, Dependencies, Security Requirements, Explicit Non-goals, Verification Requirements, Exit Conditions를 포함합니다. 빈 필드를 채우려고 완료 날짜를 추정하지 않습니다. 객체 생성은 구현 완료가 아닙니다. 필수 Issue와 종료 조건을 검증한 뒤에만 닫으며 과거 M1–M5 작업이나 Release를 근거 없이 만들지 않습니다.

구현 전에 Issue에 다음을 정의합니다.

- **Summary:** 구체적인 문제와 의도한 결과.
- **Motivation:** 작업이 필요한 이유.
- **Scope / Non-goals:** 관련 모듈과 명확한 제외 범위.
- **Acceptance Criteria:** 미완료 의존 작업의 완료를 가정하지 않고 관찰·검증할 수 있는 조건.
- **Security & Compatibility:** 권한, 데이터, 계약과 Migration 영향.
- **Validation:** 정상·오류·회귀·경계와 관련 동시성 검사.
- **Dependencies:** 실제 선행 Issue/Milestone 또는 해당하지 않는다는 설명.

유지관리자 주도 작업의 담당자는 `casing1`이며 다른 기여자의 유효한 담당자를 보존합니다. GitHub UI/API/CLI에서 실제 Milestone과 적절한 라벨을 적용한 뒤 재조회합니다. 템플릿 본문만으로 메타데이터가 설정되지 않습니다. 외부 기여자와 Dependabot은 유지관리자 분류 전에 PR을 열 수 있습니다. 유지관리자가 병합 전에 Issue와 메타데이터를 보완하고 작성자 정보를 보존하며 추가 쓰기 권한을 부여하지 않습니다.

## 라벨, 브랜치와 제목

| 구분 | 라벨 | 적용 |
| --- | --- | --- |
| 작업 유형 | `enhancement`, `bug`, `documentation`, `maintenance`, `security`, `testing`, `performance` | Issue와 PR의 실제 변경 유형 |
| 영역 | `area:framework`, `area:api`, `area:broker`, `area:runner`, `area:database`, `area:frontend`, `area:ci`, `area:docs` | Issue와 PR에 관련 영역만 사용 |
| 우선순위 | `priority:P0`, `priority:P1`, `priority:P2` | 주로 Issue에 적용: 최우선, 주요 개발, 후속 개선 |

기존 라벨과 유효한 메타데이터를 먼저 확인하고 보존합니다. `security`는 보안 관련 작업 표시이며 취약점 확정 판정이 아닙니다. 여러 영역의 PR에는 관련 영역을 복수 지정할 수 있고 Issue 우선순위를 모든 PR에 반복할 필요는 없습니다.

`feat/123-judge-heartbeat`나 `docs/124-runner-contract`처럼 Issue 번호가 포함된 집중된 브랜치를 사용합니다. `main` 직접 개발·Push는 금지합니다. Commit과 PR 제목은 간결한 영어 Conventional Commits 형식 `<type>(<scope>): <summary>`를 사용합니다. 허용 type은 `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `ci`, `build`, `chore`입니다. `changes` 같은 모호한 제목보다 `fix(broker): reject expired execution authority`처럼 실제 변경을 설명합니다.

## 변경별 필수 단계

| 단계 | 요구 결과 | 근거 |
| --- | --- | --- |
| 0. Preflight / 추적 | 브랜치, 최신 main, PR, Alert, 계약, 테스트와 실제 Milestone/Issue를 확인하고 Issue 연결 브랜치 사용 | 실제 링크와 위험 기록 |
| 1. 설계 / 기준선 | 수용 조건, 경계, Rollback과 필요한 성능 기준선 정의 | 계획, 명령과 측정 |
| 2. 구현 | 작은 단위로 동작 변경, Framework/Platform 경계와 Migration 유지 | 집중된 Diff와 테스트 |
| 3. 검증 | 관련 테스트 후 회귀, DB/Frontend와 실제 로컬 Smoke 수행 | 명령, 개수와 Skip |
| **4. 최적화 / 강화** | **모든 변경과 Milestone에서 명시적 검토** | Before/After 또는 무변경 근거 |
| 5. 문서 | README/CHANGELOG, 계약·운영 문서·보고서·목차와 영문/국문 일치 | 변경 또는 미변경 사유 |
| 6. 전달 | PR 메타데이터·실제 리뷰·Required Checks 확인 후 Squash Merge, Issue/Milestone 재조회 | PR/CI 링크와 실제 최종 상태 |

## 필수 Optimization & Hardening

동작하는 구현 이후, 최종 검증과 병합 전에 수행합니다. 큰 Milestone은 별도 단계를 배정하고 보고서에 기록합니다. 근거를 검토하는 과정이며 불필요한 코드 변경을 강제하지 않습니다.

- **성능:** 의미 있는 작업의 실행 시간과 지연, SQL 개수·인덱스, 잠금 경합, Worker 처리량·공정성, 파일·메모리, 네트워크·모델 호출과 Frontend Bundle.
- **효율성:** 불필요한 의존성, 반복 직렬화·I/O, 과도한 Trace, 중복 요청·Polling과 DB 왕복.
- **보안·안정성:** 리팩터링 후 인가, 트랜잭션·Lease 무결성, 자원 제한, 비밀정보 노출, 취소·실패와 Cleanup.
- **유지보수성:** 불필요한 추상화, 중복 로직, 모듈 경계, API 명확성, Type과 오류 안내.

가설과 기준선의 Script/Test, 데이터·작업량, 환경, 반복 횟수와 단위를 정합니다. 개선이 정당화되면 수정 전후 동일 조건에서 측정하고 잡음이 있으면 여러 회차 또는 범위를 제시합니다. 변경 후 정확성과 회귀를 확인하고 Trade-off를 기록합니다. 최적화가 불필요하거나 의미 있게 측정할 수 없으면 **"reviewed; no justified optimization"**과 이유를 기록합니다. 임의의 속도 향상을 만들지 않습니다. 보고서의 구현, 최적화, 검증을 구분하고 Mock LLM 결과를 실제 모델 성능으로 해석하지 않습니다.

## PR마다 README 검토

개발자나 평가자가 설치·사용·설정·실행·기대하거나 안전하게 배포할 수 있는 범위가 바뀌는지 확인합니다. 기능, API/흐름, 설정, 지원 환경, 상태, 한계나 Milestone이 바뀌면 같은 PR에서 README와 관련 예제·링크를 갱신합니다. 계약, Schema, 보안 경계, Migration, 운영·테스트 지침은 상세 문서에도 반영합니다. 사용자 영향 없는 내부 리팩터링·의존성 수정·문서 정리는 README를 바꾸지 않을 수 있지만 PR에 **"README reviewed; unchanged because …"** 이유를 씁니다. 계획을 구현된 기능으로 광고하지 않습니다.

## PR 작성과 리뷰

[PR 템플릿](../../../../.github/PULL_REQUEST_TEMPLATE.md)의 Summary, Linked Issue & Milestone, Update Type, Implementation Details, Verification, Optimization & Hardening, Documentation, Compatibility & Security, Limitations, Checklist를 채웁니다. 문제와 필요성, 결과 동작과 설계, 범위·비목표, 실제 검증 명령·수치, 최적화 근거, 문서 판단, 보안·호환성·Migration·Rollback과 한계를 설명합니다.

수용 조건을 모두 해결하면 `Closes #123`, 일부 작업이면 `Refs #123`를 사용합니다. PR에 실제 작업 유형과 영역 라벨, 담당자, Issue와 같은 Milestone을 지정합니다. 생성과 관련 수정 후 재조회하며 기존의 유효한 라벨·담당자를 보존합니다. 구현·검증이 바뀌면 본문도 수정하고 정확한 CI 링크와 해당하지 않는 체크 항목의 이유를 남깁니다. CLI/API PR도 템플릿을 명시적으로 채웁니다.

구현 중에는 Draft를 사용하고 자체 검증 후 Ready로 전환합니다. 실제 리뷰와 미해결 Thread를 읽고 설정된 Codex 리뷰도 실제 실행됐을 때만 실행 결과로 기록합니다. 미지원·미실행 리뷰는 그대로 보고합니다. 발견 사항을 해결하고 관련 검사를 재실행한 뒤 Squash Merge합니다. 메타데이터 자동 검사는 읽기 전용 권한을 사용하고 `pull_request_target`에서 기여자 코드를 실행하거나 쓰기 권한을 부여하지 않습니다. 외부·Bot PR 검사는 분류 전 권고 사항이며, 유지관리자는 병합 전 추적 정보를 확인합니다. 기존 필수 CI와 CodeQL은 모든 PR에 계속 적용합니다.

메타데이터 Job은 신뢰된 PR Base SHA의 검사기를 실행하고 현재 GitHub 메타데이터를 조회합니다. 최초 Governance PR의 이전 Base에는 검사기가 없으므로 Bootstrap Job이 한계를 보고합니다. 해당 PR은 `python3 scripts/check-pr-metadata.py --repository casing1/praxioj --number N`을 수동 실행합니다. 이후 PR은 병합된 Base의 검사기를 사용합니다. Bootstrap은 기존 필수 검사나 수동 메타데이터 확인을 면제하지 않습니다.

## 문서와 CHANGELOG

영문은 원본, 한국어는 유지관리 번역입니다. 신규 주요 기술 문서는 언어 간 양방향 링크와 [목차](../../../README.md)에 등록합니다. 실질적으로 바뀐 핵심 문서는 같은 PR에서 유지관리 번역도 갱신합니다. 식별자, 명령, API 경로와 기술명을 잘못 번역하지 않습니다. 기존 미번역 문서는 별도 Issue로 범위를 정합니다. [문서 템플릿](../../../templates/design.md)은 작성 기준이며 불필요한 절은 제거하거나 해당하지 않는 이유를 씁니다. 비어 있는 템플릿은 검증 근거가 아닙니다.

모든 PR에서 README와 함께 CHANGELOG를 검토합니다. 사용자에게 중요한 기능·호환성·보안·운영 변경은 `Unreleased`에 기록합니다. 모든 리팩터링을 복제하거나 발행하지 않은 버전·Tag를 만들지 않습니다. 순수 내부 변경이면 미변경 이유를 기록합니다. README, CHANGELOG, 로드맵, 상세 계약, 영문/국문과 보고서는 계획이 아닌 실제 구현 상태와 일치해야 합니다.

## 병합과 Milestone 종료

보호된 `main` Ruleset, Strict Required Checks와 CodeQL을 유지합니다. 우회, Scanner 비활성화, Force Push나 공유 이력 재작성은 금지합니다. 최신 PR Head와 필수 검사, 실제 리뷰를 확인하고 본문을 갱신한 뒤 Squash Merge합니다. 병합한 PR, 연결 Issue 상태와 Milestone 진행률을 재조회합니다. 필수 수용·종료 조건의 근거가 확보된 뒤에만 Milestone을 닫습니다. 실제 격리 수용 시험 전 M6-B는 열린 상태를 유지합니다. 최종 보고는 실제 GitHub 링크와 로컬·CI·보안 리뷰·Skip·미검증 범위를 구분합니다.

## 품질 검사와 정직한 보고

- `make test`의 Python·Frontend 테스트와 Build, 필요 시 폐기 가능한 PostgreSQL DB 검증을 수행합니다.
- 로컬 스택 변경은 현재 Milestone을 포함한 관련 Smoke를 실행하며 Mock UI 테스트로 전체 통합을 대신하지 않습니다.
- 기존 CI와 CodeQL을 사용합니다. 기본 검증에 실제 Provider API Key나 유료 호출을 사용하지 않습니다.
- 실패한 Required Check를 병합하거나 테스트를 억제해 경고를 숨기지 않습니다. 환경 제약으로 실행하지 못하면 **not run**으로 보고합니다.
- Apache-2.0과 제3자 라이선스 요구를 준수합니다.
