# GitHub 개발 관리 기반 — 검증 기록

[English](../../../development/validation-governance.md) · [문서 목차](../index.md)

## 대상과 상태

M6-A Runtime 개발 전에 [Issue #16](https://github.com/casing1/praxioj/issues/16)의 별도 Governance 변경으로 재사용 가능한 개발 규칙·문서 표준·경량 검사를 제공한다. 완료된 제품 기준선은 M5다. Heartbeat·보존·원격 Runner·Linux 사전 점검 구현은 후속 기능 PR에서 진행한다. 추적 객체의 생성만으로 수용 기준이 충족되지는 않는다.

## Commit과 환경

Preflight에서 로컬·원격 `main`은 M5 완료 Commit `cb05a77207a2034b0488a16f601b1ddc51026798`로 일치했고 작업 트리는 깨끗했다. `docs/16-github-governance` Branch에서 보호된 main, 기존 데이터와 PostgreSQL Volume을 보존한다. 최종 PR 전달 기록에 실제 테스트 Head, Squash Merge 리비전과 원격 CI 링크를 남기며 이 문서에서 미래 Commit Hash를 만들지 않는다.

로컬 기준선은 macOS arm64, Python 3.13.5, Node 24.11.0, Docker PostgreSQL 18.6이다. 실제·유료 Provider 호출, 자격증명, 실제 참가자 데이터, 공개 배포나 비신뢰 코드 실행을 사용하지 않았다.

## 기준선과 회귀 증거

M6-A Runtime 변경 전 유지관리자가 다음 결과를 확보했다.

| 검사 | 실제 결과 |
| --- | --- |
| 합성 백업·복구를 포함한 PostgreSQL Python | 404 passed, 1 live-provider skip; 107.17 s |
| 권한이 허용된 SQLite Python 재실행 | 384 passed, 21 skipped; 64.38 s |
| Frontend | 33 passed; 3.67 s |
| TypeScript/Vite | 통과; JS 274.37 kB / gzip 82.90 kB, CSS 31.23 kB / gzip 7.45 kB |
| `pip check`, 포함 라이선스 동기화, Compose 설정 | 통과 |
| 새 Governance 검사 도구 테스트 | 25 passed; 세부 동작은 PR에 기록 |

최초 SQLite 실행은 도구 제한 환경에서 로컬 Fixture Socket을 열지 못해 58.32 s에 341 passed, 21 skipped, 43 setup errors였다. 위의 허용된 로컬 재실행은 통과했다. 관찰 후 해결한 환경 제약이며 제품 실패를 숨긴 것이 아니다. SQLite Skip에는 PostgreSQL 전용 동시성 검사와 자격증명·실제 호출 또는 환경 의존 검사가 포함되며 정확한 목록은 실행 출력에 따른다. SQLite는 PostgreSQL Lock 검증이 아니다.

Governance Diff는 정책·문서·Issue/PR 템플릿과 관련 검사만 바꾸며 제품 Runtime과 의존성을 바꾸지 않는다. 기존 Smoke·Compose Runtime 경로는 유지한 필수 CI Stack 검사에서 실행한다. 결과는 실제 PR 실행에서 확인하며 기준선 테스트만으로 추정하지 않는다.

## GitHub 객체와 메타데이터

아래 객체를 실제 생성·재조회했으며 `casing1` 담당자와 적절한 작업 유형·영역·우선순위 라벨을 지정했다. 날짜를 강제하지 않았고 기존 동등한 라벨은 보존했다.

| 객체 | 범위 |
| --- | --- |
| [M6-A](https://github.com/casing1/praxioj/milestone/1) | Judge Lifecycle & Remote Runner Foundation |
| [#16](https://github.com/casing1/praxioj/issues/16) | 개발 관리·문서 표준 |
| [#17](https://github.com/casing1/praxioj/issues/17) | Judge Heartbeat·Lease 갱신 |
| [#18](https://github.com/casing1/praxioj/issues/18) | Judge 보존·Purge·할당량 회수 |
| [#19](https://github.com/casing1/praxioj/issues/19) | 원격 Runner 프로토콜·인증 경계 |
| [#20](https://github.com/casing1/praxioj/issues/20) | Linux 호환성·격리 사전 점검 |
| [#21](https://github.com/casing1/praxioj/issues/21) | 수명주기 보안·PostgreSQL 동시성 시험 |
| [#22](https://github.com/casing1/praxioj/issues/22) | M6-A 문서·최적화·최종 검증 |
| [M6-B](https://github.com/casing1/praxioj/milestone/2) | 별도의 Open Linux Runner 격리 검증 |
| [#23](https://github.com/casing1/praxioj/issues/23), [#24](https://github.com/casing1/praxioj/issues/24), [#25](https://github.com/casing1/praxioj/issues/25), [#26](https://github.com/casing1/praxioj/issues/26), [#27](https://github.com/casing1/praxioj/issues/27) | 전용 호스트·Runtime 격리, 자원 제한, 네트워크 차단, Cleanup, 독립 보안 수용 시험을 위한 Open 계획 작업 |

라벨 정책은 `enhancement`, `bug`, `documentation`, `maintenance`, `security`, `testing`, `performance`; 실제 관련 영역 `area:framework`, `area:api`, `area:broker`, `area:runner`, `area:database`, `area:frontend`, `area:ci`, `area:docs`; Issue 우선순위 `priority:P0/P1/P2`를 사용한다. `security`는 작업 분류이지 취약점의 확정 증거가 아니다. PR 본문은 실제 메타데이터를 대신하지 않는다. PR 생성 뒤와 병합 전에 라벨·담당자·일치한 Milestone·연결 Issue를 다시 조회한다.

## 구현과 문서

- 루트 AGENTS·CONTRIBUTING·개발 절차에 Issue 우선 작업, Issue 번호 Branch, Conventional Commit PR 제목, 실제 메타데이터 확인, 영문·국문 일관성, README/CHANGELOG 검토와 별도 최적화·보안 강화 단계를 반영했다.
- Issue·PR 템플릿에 수용 기준, 의존성, 검증, 보안·호환성, 한계와 전달 증거를 포함했다.
- [문서 정책](documentation-policy.md), [목차](../index.md), 문서 템플릿 4종과 명시적 번역 목록으로 영문 원본·유지되는 한국어 대응을 관리한다. 기존 경로와 과거 영문 기록은 보존한다.
- README·CHANGELOG는 현재 기능과 향후 추적을 구분한다. 과거 이력은 실제 PR·검증 보고서에 근거하며 릴리스·태그를 만들지 않는다.
- [AuthZest 분석](governance-reference.md)은 소스 근거를 고정하고 PraxiOJ 고유의 Squash 정책·도구 체계·개인 소유·보안 경계를 유지한다.

## 보안·최적화 검토

새 도구는 최소 읽기 권한으로 문서와 PR 메타데이터를 검사한다. 높은 권한으로 신뢰할 수 없는 PR 코드를 Checkout하거나 권한 부여·GitHub 객체 자동 변경·Bot 또는 외부 기여자 권한 확대를 하지 않는다. 기존 필수 검사 이름·보안 Scanner를 유지한다. 외부 기여자·Dependabot의 작성자 출처를 보존하며 저장소 쓰기 권한 없이 메타데이터를 처리할 절차를 문서화한다.

제품 Runtime은 reviewed; no justified optimization이다. 이 변경에는 최적화할 제품 DB Query·Lease·요청 직렬화 변경이 없다. 문서 검사는 로컬에서 결정적으로 수행하며 외부 URL 크롤링이나 의존성을 추가하지 않는다. 도구 테스트는 정상·거부·경계 동작을 검사하며 애플리케이션 지연 개선을 주장하지 않는다.

## CI·한계·종료 조건

Squash Merge 전에 필수 CI/CodeQL과 실제 리뷰 결과를 확인한다. 최종 링크와 결과는 Governance PR 전달 기록에 남긴다. 문서 작성 시점의 원격 결과·최종 Merge 리비전은 대기 중이며 자동 Codex 리뷰를 가정하지 않는다.

오프라인 링크·번역 검사는 번역 의미·외부 URL 가용성·운영 안전성을 입증하지 않는다. 이 Governance 단계에서 M6-A Runtime과 OS 수준 M6-B 격리는 미구현이다. M6-A는 필수 작업의 해결·검증까지 Open이며 M6-B는 전용 Linux 수용 시험까지 Open이다. 과거 M1–M5를 소급 완료한 Milestone·Issue는 만들지 않았다.


최종 전달: [PR #28](https://github.com/casing1/praxioj/pull/28)은 필수 검사 성공 후 `5e47b4976e91e0310016d3dd09839efc78636da2`로 병합됐습니다. 최종 CI는 429 passed/1 skip이며 CodeQL과 추가 Governance 검사도 성공했고 Issue #16은 종료됐습니다. 이후 M6-A 구현은 별도 [PR #29](https://github.com/casing1/praxioj/pull/29)로 진행했으며 현재 제품 상태는 [M6-A 검증](validation-m6a.md)을 참고합니다. 위의 대기 표현은 작성 시점의 범위를 나타내며 현재 전달 상태가 아닙니다.
