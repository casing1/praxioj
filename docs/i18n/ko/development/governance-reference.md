# AuthZest 개발 절차 참고와 PraxiOJ 적용 결정

[English](../../../development/governance-reference.md) · [문서 목차](../index.md)

## 목적과 상태

[Issue #16](https://github.com/casing1/praxioj/issues/16)에서 PraxiOJ의 지속적인 GitHub 개발 절차를 정립할 때 사용한 근거를 기록한다. 별개의 공개 프로젝트 운영 방식에 대한 분석이며 제품 설계를 이전하거나 M6-A 구현 완료를 주장하는 문서가 아니다. 이 Governance PR의 완료된 제품 기준선은 M5다. PraxiOJ의 규범은 [개발 절차](engineering-workflow.md)다.

## 검토한 근거

AuthZest의 `36bf3831d59039a73bde432da404dca14965b298` Commit을 조사했다. 아래 파일 링크는 해당 Snapshot에 고정되어 있다. GitHub 메타데이터는 이번 작업 중 조회한 상태이며 이후 달라질 수 있다.

| 자료 | 관찰한 운영 방식 |
| --- | --- |
| [CONTRIBUTING.md](https://github.com/casing1/authzest/blob/36bf3831d59039a73bde432da404dca14965b298/CONTRIBUTING.md), [Branch 규칙](https://github.com/casing1/authzest/blob/36bf3831d59039a73bde432da404dca14965b298/docs/development/BRANCH_RULES.md) | Issue와 연결한 기능 Branch, Conventional Commits, 기여자와 검토자의 명시적 책임 |
| [PR 템플릿](https://github.com/casing1/authzest/blob/36bf3831d59039a73bde432da404dca14965b298/.github/pull_request_template.md) | 구체적인 범위·검증·메타데이터·문서 정보 |
| [CHANGELOG.md](https://github.com/casing1/authzest/blob/36bf3831d59039a73bde432da404dca14965b298/CHANGELOG.md) | 구현 상세와 구분한 사용자 영향 중심의 변경 이력 |
| [문서 목차](https://github.com/casing1/authzest/blob/36bf3831d59039a73bde432da404dca14965b298/docs/README.md), [개발 계획](https://github.com/casing1/authzest/blob/36bf3831d59039a73bde432da404dca14965b298/docs/development/DEVELOPMENT_PLAN.md), [한국어 문서](https://github.com/casing1/authzest/tree/36bf3831d59039a73bde432da404dca14965b298/docs/i18n/ko) | 탐색 가능한 구조, 언어 간 상호 링크, 계획과 실제 구현의 구분 |
| [Milestone](https://github.com/casing1/authzest/milestones?state=all), [Issue](https://github.com/casing1/authzest/issues), [라벨](https://github.com/casing1/authzest/labels) | 실제 Milestone 6개: 1–3 Closed, 4–6 Open, 완료 예정일 없음. 작업 유형·컴포넌트 라벨과 실제 담당자 지정 |
| 최근 [PR #167](https://github.com/casing1/authzest/pull/167), [#166](https://github.com/casing1/authzest/pull/166), [#165](https://github.com/casing1/authzest/pull/165) | 실제 `casing1` 지정, `06 - Evaluation and course delivery` Milestone 일치, 변경 유형·영역 라벨, 부분 작업인 [#152](https://github.com/casing1/authzest/issues/152)·[#150](https://github.com/casing1/authzest/issues/150) 등에 `Refs` 연결 |

저장소 메타데이터에서 AuthZest는 Merge Commit을 허용했다. PraxiOJ는 기존 Squash 전용 정책과 보호된 main의 필수 검사를 유지한다. 제품 코드·라이선스 고지·도메인 보안 가정을 복사하지 않고 운영 아이디어를 PraxiOJ에 맞는 새 문장으로 정리한다.

## 채택한 방식과 차이

| 방식 | PraxiOJ 결정 |
| --- | --- |
| Issue로 작업 정의 | Milestone → 수용 기준을 갖춘 Issue → Issue 번호가 포함된 기능 Branch → PR → 검증 → 보호된 Squash Merge 순서다. Governance 변경부터 적용한다. |
| 실제 메타데이터 일치 | Issue·PR의 적절한 라벨·담당자·동일 Milestone을 설정·재조회하고 기존의 유효한 메타데이터와 기여자·Bot 출처를 보존한다. 템플릿 본문은 메타데이터를 설정하지 않는다. |
| 변경 명명 | 영문 PR 제목은 `<type>(<scope>): <summary>`다. 완결 작업은 `Closes`, 부분 작업은 `Refs`를 쓰며 미완료 Issue를 닫지 않는다. |
| 구체적인 검토 증거 | 기존 필수 CI/CodeQL 5개를 유지하고 실제 리뷰를 확인하며 최종 테스트 뒤 PR을 갱신한다. 자동 Codex 리뷰가 실행됐다고 가정하지 않는다. |
| 문서 이력 | 문서 목차·템플릿·`Unreleased` 변경 이력·범위를 정한 영문/국문 대응을 도입한다. 과거에 없던 릴리스 태그를 만들거나 기존 문서를 한 번에 전부 번역하지 않는다. |
| 프로젝트별 제약 | Python 3.13, Node 24, 독립적인 Framework/Platform 경계, Apache-2.0과 개인 소유를 유지한다. AuthZest Runtime 선택·제품 도메인·Merge Commit 규칙을 가져오지 않는다. |
| 보안·자원 | localhost 개발, 유료·실제 LLM 호출 금지와 비신뢰 코드 실행 금지를 유지한다. 합성 프로토콜 검증은 OS 격리를 입증하지 않는다. |

## 실제 추적 객체와 수용 기준

Governance 변경은 [M6-A — Judge Lifecycle & Remote Runner Foundation](https://github.com/casing1/praxioj/milestone/1)의 [Issue #16](https://github.com/casing1/praxioj/issues/16)에서 관리한다. 구현은 [Heartbeat #17](https://github.com/casing1/praxioj/issues/17), [보존 #18](https://github.com/casing1/praxioj/issues/18), [원격 프로토콜 #19](https://github.com/casing1/praxioj/issues/19), [Linux 사전 점검 #20](https://github.com/casing1/praxioj/issues/20), [보안·동시성 시험 #21](https://github.com/casing1/praxioj/issues/21), [문서·최적화·검증 #22](https://github.com/casing1/praxioj/issues/22)로 나눈다. 객체 생성은 추적 근거이며 구현 수용의 증거가 아니다.

[M6-B — Isolated Linux Runner Validation](https://github.com/casing1/praxioj/milestone/2)은 별도의 Open 범위다. 계획 Issue는 [호스트·Runtime 격리 #23](https://github.com/casing1/praxioj/issues/23), [자원 제한 #24](https://github.com/casing1/praxioj/issues/24), [네트워크 차단 #25](https://github.com/casing1/praxioj/issues/25), [Cleanup #26](https://github.com/casing1/praxioj/issues/26), [독립 보안 수용 시험 #27](https://github.com/casing1/praxioj/issues/27)이다. 완료 예정일이나 OS 보안 수용 여부를 추정하지 않는다.

Governance PR은 실제 메타데이터, 결정적인 문서 검사, 적절한 회귀 검사와 모든 필수 CI/CodeQL 결과를 확보한 뒤 Squash Merge한다. 정확한 Head·병합 리비전과 원격 실행 링크는 최종 PR 본문에 기록한다. M6-A는 필수 Issue의 구현·검증·해결 뒤에만 완료된다. M6-B는 Mock 증거만으로 닫을 수 없다.

## 최적화와 한계

제품 Runtime에 대해 reviewed; no justified optimization이다. 이 Governance PR은 절차·문서·관련 검사만 변경한다. 경량 오프라인 검사는 네트워크 의존성과 기여자 코드의 쓰기 권한을 추가하지 않는다. 번역 검사는 파일·링크 대응을 확인하며 의미 일치와 소스 정확성은 사람 또는 에이전트의 검토가 필요하다. 실제 Ruleset·경고·리뷰·검사는 이후 PR마다 다시 조회해야 한다.
