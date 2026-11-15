# PraxiOJ 기여 안내

[English — canonical source](../../../CONTRIBUTING.md)

PraxiOJ는 DoHyun Choi가 유지관리하는 독립적인 개인 취미 오픈소스 프로젝트입니다. 대학, 연구실 또는 기업의 공식 프로젝트가 아닙니다. 프로젝트명과 Apache License 사용은 Apache Software Foundation이나 다른 기관의 후원·보증·소속을 의미하지 않습니다. 버그 보고, 문서, 테스트와 범위가 명확한 코드 기여를 환영합니다.

## 문제 정의부터 시작하기

개발 순서는 **Milestone → Issue → Feature Branch → PR → Validation → Squash Merge**입니다. 기존 GitHub Milestone, Issue와 PR을 먼저 확인하고, 같은 목적의 객체를 재사용합니다. 작은 수정도 구현 전에 Issue로 정의합니다. Issue에는 Summary, Motivation, Scope, Non-goals, 검증 가능한 Acceptance Criteria, Security & Compatibility, Validation, Dependencies를 작성합니다. 버그는 기대 동작, 실제 동작, 버전과 최소 재현 절차도 포함합니다. 예제와 로그에서 자격증명, 참가자 데이터와 비공개 제출물을 제거합니다.

주요 개발 단계는 실제 GitHub Milestone으로 관리합니다. Markdown 제목만으로는 관리 객체가 생성되지 않습니다. 이름은 `M6-A — Judge Lifecycle & Remote Runner Foundation`, `M6-B — Isolated Linux Runner Validation`, 이후 `M7 — …` 형식을 사용합니다. Objective, Scope, Deliverables, Acceptance Criteria, Dependencies, Security Requirements, Explicit Non-goals, Verification Requirements, Exit Conditions를 설명합니다. 임의의 완료 날짜를 만들거나 근거 없는 과거 작업을 완료 처리하지 않습니다. 필수 Issue와 종료 조건을 검증한 뒤에만 Milestone을 닫습니다.

유지관리자는 Issue의 작업 유형, 관련 `area:*`, 우선순위와 실제 Milestone을 설정합니다. 유지관리자 주도 작업의 기본 Assignee는 `casing1`이며 기존의 유효한 담당자와 라벨을 보존합니다. 외부 기여자와 Dependabot은 분류 전에 PR을 열 수 있습니다. 유지관리자가 병합 전에 추적 정보와 메타데이터를 보완하며, 작성자 정보를 보존하고 기여를 위해 추가 쓰기 권한을 요구하지 않습니다. 라벨과 실제 메타데이터 확인 방법은 [개발 절차](development/engineering-workflow.md)를 따릅니다.

[아키텍처](../../../docs/architecture/overview.md), [모듈 경계](../../../docs/architecture/module-boundaries.md), [로드맵](../../../docs/development/roadmap.md)을 읽어 주세요. 현재 단계는 운영 수준 인증, 비신뢰 코드 실행과 외부 평가자 실행을 제공하지 않습니다.

## 개발과 검증

저장소를 Fork하고 `feat/123-judge-heartbeat`처럼 Issue 번호가 포함된 기능 브랜치를 사용합니다. `main`에서 직접 개발하지 않습니다. Commit과 PR 제목은 간결한 영어 Conventional Commits 형식 `<type>(<scope>): <summary>`를 사용합니다. 허용 type은 `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `ci`, `build`, `chore`입니다. 지원 환경과 명령은 [로컬 설정](../../../docs/development/local-setup.md)을 따릅니다. 루트 [Makefile](../../../Makefile)은 `make install`, `make test`, `make api`, `make web`과 Compose 명령을 제공합니다.

- Framework는 FastAPI, SQLAlchemy, React와 Platform 비밀정보에 의존하지 않아야 합니다. Provider, Tool, Evaluator와 Execution Backend는 각 계약을 통해 확장합니다.
- 새 문제는 검증된 `manifest.json` 디렉터리로 제공합니다. Manifest를 통해 API가 임의 Python 코드를 import하게 해서는 안 됩니다.
- Session이 참조하는 문제 버전을 보존합니다. Manifest/Event Schema, Migration과 버전 변경 및 미구현 동작을 문서화합니다.
- 동작 변경과 회귀에 필요한 테스트를 추가하고 명령·계약·한계가 바뀌면 문서도 갱신합니다.

`make test`로 Python, Frontend 테스트와 Build를 실행합니다. 관련 검사를 실행하지 못했다면 통과로 기록하지 않습니다. 영속성·Migration·잠금 변경은 [로컬 설정](../../../docs/development/local-setup.md)의 폐기 가능한 PostgreSQL 테스트 DB에서도 검증합니다. SQLite 통과는 PostgreSQL 트랜잭션 검증이 아닙니다. API/UI 통합 변경은 실행 중인 로컬 스택과 관련 Smoke Script를 확인하며 `scripts/smoke.py`, `scripts/smoke-m2.py`의 기존 흐름을 보존합니다. 컴포넌트 테스트만으로 전체 흐름 검증을 대신하지 않습니다. Provider 기본 검증은 Mock 또는 로컬 Fixture를 사용하며 실제 자격증명과 네트워크가 필요한 검사는 명시적 Opt-in과 Skip 사유를 유지합니다.

## 필수 최적화·문서 검토

모든 변경은 [개발 절차](development/engineering-workflow.md)와 [AGENTS.md](../../../AGENTS.md)의 Preflight, 설계·기준선, 구현, 검증, **Optimization & Hardening**, 문서와 PR 전달 단계를 따릅니다. 병합 전에 DB 왕복과 잠금, 지연, 메모리·자원, 중복 작업, 보안·안정성, 유지보수성을 검토합니다. 성능 개선을 주장하면 동일 조건의 Before/After를 측정합니다. 정당한 최적화가 없으면 **"reviewed; no justified optimization"**과 이유를 기록합니다.

모든 PR에서 **README와 CHANGELOG를 검토**합니다. 기능, 설치·실행 명령, 설정, 아키텍처 요약, Milestone 상태와 한계가 달라지면 README를 갱신합니다. 사용자에게 중요한 기능·호환성·보안 변경은 CHANGELOG의 `Unreleased`에 기록합니다. 순수 내부 유지보수로 갱신하지 않는 경우 PR에 이유를 씁니다. 발행하지 않은 Release나 Tag를 만들지 않습니다.

영문은 원본이며 한국어는 유지관리 번역입니다. 신규 주요 기술 문서는 양방향 언어 링크와 [문서 목차](../../../docs/README.md) 항목을 추가하고, 실질적으로 바뀐 핵심 문서의 유지관리 번역도 동기화합니다. 코드 식별자, 명령과 API 경로를 바꾸지 않습니다. 기존 미번역 문서는 별도 Issue로 범위를 정하며 관련 없는 대규모 번역을 수행하지 않습니다. 계약, 로드맵, 보안 문서와 검증 보고서는 실제 구현과 일치해야 합니다.

Milestone 완료 전 별도의 최적화·강화 단계를 수행하고, 무변경 판단의 근거, 측정 한계, 검증과 위험을 보고서에 남깁니다. 비교 가능한 기준선 없이 성능 향상을 주장하지 않습니다.

## PR 제출과 병합

CLI/API로 생성할 때도 [.github/PULL_REQUEST_TEMPLATE.md](../../../.github/PULL_REQUEST_TEMPLATE.md)를 따릅니다. 문제, 결과 동작, 구현과 실제 검증을 설명합니다. 완전히 해결한 Issue는 `Closes #123`, 일부 작업은 `Refs #123`로 연결합니다. 실제 작업 유형·영역 라벨, 담당자와 연결 Issue와 같은 Milestone을 설정하고 생성·수정 후 GitHub에서 재조회합니다. 본문 텍스트는 메타데이터를 적용하지 않습니다. 시각적 검토에 도움이 되면 스크린샷을 첨부하며 Migration, 호환성과 한계를 설명합니다. 관련 없는 정리는 별도로 분리합니다.

구현 중에는 Draft PR을 사용하고 자체 검증 뒤 Ready로 전환합니다. 실제 Required CI, CodeQL, 제출된 리뷰와 미해결 Thread를 확인합니다. 자동 코드·보안 리뷰가 실행됐다고 가정하지 않습니다. 발견 사항을 수정하고 관련 검사를 재실행하며 최종 PR 본문을 갱신합니다. 외부·Bot 메타데이터 검사는 유지관리자 분류 전에는 권고 사항이지만 리뷰와 필수 검사를 면제하지 않습니다. 모든 Required Checks 성공 후 보호된 `main` 규칙을 우회하지 않고 Squash Merge합니다. Force Push, 공유 이력 재작성과 Scanner 약화는 금지합니다. 병합 후 Issue 상태와 Milestone 진행률을 GitHub에서 다시 확인하고 결과를 보고합니다.

로컬 `.env`, Cookie, Token, 비공개 제출물, 생성된 DB, Dependency Cache와 관련 없는 생성 파일을 포함하지 않습니다. 의존성이 바뀌면 의도된 Lockfile 변경은 포함합니다. 유지관리자는 정확성, 범위, 아키텍처, 문서와 라이선스를 검토합니다. 개인 프로젝트이므로 리뷰 일정은 달라질 수 있습니다. 기술적 이견에는 근거를 제시하고 서로 존중하며 인신공격이나 괴롭힘을 하지 않습니다.

## 라이선스와 저작권

PraxiOJ는 [Apache License, Version 2.0](../../../LICENSE)을 사용합니다. 별도 서면 합의가 없다면 프로젝트에 포함할 목적으로 제출한 기여는 [License Section 5](https://www.apache.org/licenses/LICENSE-2.0)에 따라 Apache-2.0 조건으로 제공됩니다. 현재 CLA는 필요하지 않습니다. 기여자는 자신의 저작권을 보유하며 유지관리자에게 양도하지 않습니다.

원 프로젝트 고지는 `Copyright 2026 DoHyun Choi`입니다. 이 고지가 기여자나 제3자의 권리를 대체하지 않습니다. 적용되는 저작권과 출처 고지를 보존합니다.

제출 권한이 있는 코드, 문서, 테스트, Fixture, 예제와 자산만 기여합니다. 복사·수정한 제3자 자료의 출처, 버전·Revision과 라이선스를 PR 및 고지에 명시합니다. 필요한 원본 License, Notice와 수정 고지를 보존하며 Apache 라이선스 파일 수정 시 필요한 명확한 수정 고지도 포함합니다. 의존성은 각자의 라이선스를 유지하며 PraxiOJ 라이선스로 바뀌지 않습니다.

## 보안 보고

[SECURITY.md](../../../SECURITY.md)를 읽고 활성화된 [GitHub 비공개 취약점 신고](https://github.com/casing1/praxioj/security/advisories/new)를 사용합니다. 자격증명, 참가자 데이터와 실제 서비스 대상 공격 세부사항을 공개 Issue나 PR에 게시하지 않습니다.
