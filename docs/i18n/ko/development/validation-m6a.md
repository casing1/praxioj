# M6-A — Judge Lifecycle & Remote Runner Foundation 검증

[English — canonical source](../../../development/validation-m6a.md) · [문서 목차](../index.md)

## 대상, Revision과 현재 상태

M6-A는 Issue 기반 GitHub 관리 체계, 확인 응답을 제공하는 Judge Lease 갱신, 제한된 Terminal 기록 보존, 합성 Runner 통신 경계와 실행하지 않는 Linux 사전 점검을 구현합니다. 이 기록은 구현, 관찰한 테스트, 최적화와 전달 상태를 구분합니다. 현재 구현 단계의 기록에서는 로컬 검증과 독립적인 관리형 보안 검토를 완료했으며, 보호 규칙을 따르는 기능 PR 전달과 최종 Milestone 승인은 진행 중입니다. 최종 수용 전에 실제 결과를 기록해야 합니다. M6-B는 열린 상태이며 미구현입니다.

2026-11-15(Asia/Seoul) 사전 점검에서 로컬·원격 M5 main `cb05a77207a2034b0488a16f601b1ddc51026798`이 깨끗한 상태이고, 열린 PR·Issue·Milestone과 열린 Dependabot·CodeQL·Secret Scanning Alert가 모두 없음을 확인했습니다. Squash 전용 저장소 설정과 활성 main Ruleset `26909462`는 우회 담당자 없이 5개 Strict Required Checks를 유지합니다. 기존 참가자 데이터나 PostgreSQL Volume을 초기화하지 않았습니다.

Governance는 제품 변경에 앞서 `docs/16-github-governance`에서 구현했습니다. [PR #28](https://github.com/casing1/praxioj/pull/28)의 최종 Head는 `e17d2bd300d624d75514e135a0bcec2366df2a59`, 보호 규칙을 따른 Squash Commit은 `5e47b4976e91e0310016d3dd09839efc78636da2`입니다. 기능 작업은 병합된 main을 기준으로 `feat/17-judge-lifecycle-runner`에서 시작합니다. Lifecycle과 Runner는 갱신·취소 확인 계약을 공유하므로 그 경계를 함께 검증하는 하나의 기능 PR로 전달하고, 최종 문서와 GitHub 수용 절차는 별도 PR로 수행합니다. 정확한 기능 Head·Merge·검사 링크는 해당 PR 전달 기록과 아래 최종 전달 절에 기록합니다.

Native 환경은 macOS 27.0.1 arm64, Python 3.13.5, Node 24.11.0이며 로컬 Docker PostgreSQL은 18.6입니다. Compose는 저장소에 고정된 개발용 Image를 사용합니다. 아래 시간은 공유 개발 호스트에서 관찰한 값이며 운영 지연·처리 용량의 보장이 아닙니다. 테스트는 무작위의 폐기 가능한 Schema와 합성 Backup/Restore DB를 사용합니다. 실제·유료 모델, 생성한 API Key, 실제 참가자 데이터, 공개 배포와 비신뢰 코드 실행을 사용하지 않았습니다.

## GitHub 관리 체계와 실제 객체

AuthZest [참고 분석](governance-reference.md)은 확인한 소스와 실제 Issue·PR 메타데이터를 기록합니다. 작업 추적·검증과 영문·국문 문서 관리 방식을 참고하면서 PraxiOJ의 Squash 정책, 지원 버전, 프로젝트 도메인과 독립 개인 Apache-2.0 저작권을 유지합니다.

| 실제 객체 | 구현 검증 시점의 범위와 상태 |
| --- | --- |
| [M6-A Milestone 1](https://github.com/casing1/praxioj/milestone/1) | 필수 Issue와 최종 종료 조건을 모두 검증할 때까지 Open |
| [#16](https://github.com/casing1/praxioj/issues/16) / [PR #28](https://github.com/casing1/praxioj/pull/28) | 제품 변경 전에 Governance 해결 및 Squash Merge |
| [#17](https://github.com/casing1/praxioj/issues/17), [#18](https://github.com/casing1/praxioj/issues/18) | Heartbeat·Lease와 단계별 보존·Quota 회수 |
| [#19](https://github.com/casing1/praxioj/issues/19), [#20](https://github.com/casing1/praxioj/issues/20) | Runner 경계와 Linux 사전 점검 |
| [#21](https://github.com/casing1/praxioj/issues/21), [#22](https://github.com/casing1/praxioj/issues/22) | 보안·동시성 수용과 최종 문서·최적화·검증 |
| [M6-B Milestone 2](https://github.com/casing1/praxioj/milestone/2), [#23](https://github.com/casing1/praxioj/issues/23)–[#27](https://github.com/casing1/praxioj/issues/27) | 전용 호스트·출처, 격리·Quota, 네트워크·비밀정보, 종료·정리와 독립 OS 수용 시험의 열린 계획이며 M6-B 구현은 없음 |

두 Milestone은 Objective, Scope, Deliverables, Acceptance, Dependencies, Security, Non-goals, Verification, Exit Conditions를 포함하며 임의의 Due Date를 지정하지 않았습니다. 모든 Issue의 Assignee를 `casing1`로 설정하고 실제 작업·영역·우선순위 라벨과 해당 Milestone을 재조회했습니다. 기존의 유효한 라벨은 보존했습니다. 작업 유형은 enhancement/bug/documentation/maintenance/security/testing/performance, 유지관리 영역은 Framework/API/Broker/Runner/database/frontend/CI/docs, 우선순위는 P0/P1/P2입니다. security 라벨은 취약점 확정 판정이 아닙니다. 근거 없는 M1–M5 객체·Release·Tag를 만들지 않았습니다.

AGENTS, CONTRIBUTING, 개발 절차와 템플릿은 Milestone → Issue → Issue 번호 브랜치 → PR → 검증 → Squash Merge, 실제 메타데이터 재조회, README/CHANGELOG 판단, 영문·국문 일치, 명시적 최적화·강화와 병합 후 확인을 요구합니다. 기존 검사에 추가한 읽기 전용 Governance Workflow는 신뢰된 Base 코드의 메타데이터 검사기를 실행합니다. 외부·Bot 메타데이터는 유지관리자 분류를 위한 권고 사항이며 작성자나 쓰기 권한을 바꾸지 않습니다. 최초 PR의 Base에 검사기가 없는 한계를 명시하고 실제 GitHub 메타데이터를 수동 검사했습니다. 독립 소스 검토에서 렌더링된 Anchor 정확성 문제를 발견했으며 병합 전에 회귀 테스트와 함께 수정했습니다.

## 기준선과 실제 회귀 결과

| 검사 | M6-A 제품 변경 전 | 현재 로컬 결과 |
| --- | --- | --- |
| PostgreSQL Python, 실제 합성 Backup/Restore 활성화 | 404 passed, 1 live-provider skip; 107.17 s | **510 passed, 1 live-provider skip; 144.77 s** |
| SQLite Python | 384 passed, 21 skipped; 64.38 s | **483 passed, 28 skipped; 89.81 s** |
| Frontend | 33 passed; 3.67 s | **33 passed; 3.78 s** |
| TypeScript/Vite | Passed | Passed; JS 274.37 kB / gzip 82.90 kB, CSS 31.23 kB / gzip 7.45 kB로 변화 없음 |
| Governance 도구 | 기준선 이후 추가 | 25 passed; 전달 전에 로컬 Markdown·번역 검사 실행 |
| Framework | M5 Foundation 161개 Case | 신규 Runner 21개를 포함해 182 passed |
| M5 + Lifecycle 대상 PostgreSQL | M5 유지 | 83 passed; 44.98 s |
| 신규 Lifecycle SQLite | 없음 | 32 passed, 6 PostgreSQL-only skips; 15.94 s |
| Runner 대상 PostgreSQL | 없음 | 43 passed; 12.02 s |
| Runner 대상 SQLite | 없음 | 42 passed, 1 PostgreSQL race skip; 6.79 s |

전체에 Governance 25개, Lifecycle 38개와 Runner 43개 Case가 추가됐습니다. PostgreSQL에서는 명시적 Opt-in 실제 모델 추론만 Skip합니다. SQLite의 28개 Skip은 PostgreSQL 전용 시계·잠금·프로세스 Case 26개, 실제 PostgreSQL Backup/Restore와 실제 추론입니다. SQLite를 PostgreSQL 잠금의 검증 근거로 취급하지 않습니다. 기존 Starlette/httpx TestClient 사용 중단 경고와 과거 SQLite Adapter 경고는 그대로 보이며 Scanner나 테스트를 비활성화하지 않았습니다. Suite 크기와 동시 호스트 작업이 다르므로 전체 테스트 실행 시간을 애플리케이션 성능으로 해석할 수 없습니다.

최초 제한 환경의 SQLite 기준선 실행은 로컬 Fixture Socket이 금지돼 341 passed/21 skipped/43 setup errors였으며, 이후 권한을 적용한 재실행에서 위 결과를 확인했습니다. Runner 대상 PostgreSQL 설정도 Loopback 접근 권한이 필요했고, 환경 실패를 숨기지 않고 성공한 43개 Case 재실행을 기록했습니다. 두 환경 제약을 해결하기 위해 제품 Assertion을 약화하지 않았습니다.

## 구현과 아키텍처 결정

- `JudgeBroker.renew()`는 `heartbeat() -> bool`을 유지하면서 DB에서 관찰한 Lease·Capability·Deadline 메타데이터를 반환합니다. Owner/Session/Job/Attempt 잠금 뒤 PostgreSQL `clock_timestamp()`로 권한을 확인합니다. Source·Result 검증 후 만료를 재검사하며 취소·복구로 과거 권한이 살아나지 않습니다. Dispatcher는 Mock을 기다리는 동안 갱신하고, 실행을 가로질러 DB Transaction을 유지하지 않으며 Terminal 전이 전에 갱신 Loop 종료를 기다립니다.
- Migration `0009_judge_lifecycle`은 M5 기록을 보존하고 Purge Marker·Terminal Index를 추가하며 Readiness·Backup Schema 검증을 갱신합니다. 기본 결과 보존은 7일, 메타데이터는 30일이며 정수 범위는 `1 <= result <= metadata <= 90`입니다. 제한된 Maintenance는 실행 중이거나 보호되는 권한을 보존하고 Result·비공개 Request·Attempt Payload를 정리합니다. 안전한 Assessment는 근거가 없다는 표시와 함께 유지하다가 이후 Summary도 삭제합니다. 원래 Evaluation과 Trace는 분리된 상태를 유지합니다. Payload 용량을 회수하며 전체 Metadata는 설정된 보존 Job 상한의 4배로 제한합니다. Idempotency 이력은 Job 기록과 함께 만료됩니다.
- `praxioj.execution.runner`는 별도의 엄격한 Version 1.0 Wire Contract와 `MockRunnerTransport`를 추가합니다. Framework는 새 의존성 없이 ORM·Web과 독립적입니다. 신뢰된 Platform의 `JudgeRunnerGateway`는 원래 Broker Lease를 비공개로 보유하고 별도로 관찰한 Identity와 정확한 Request/Attempt/Fence/Digest를 결합하며 최대 3개 Operation Grant Hash를 저장합니다. Heartbeat Rotation과 단일 Result 제출은 Replay를 거부합니다. 취소는 저장된 Owner 취소를 요구하며 Cleanup은 고정된 합성 무자원 상태만 수용합니다. 기본 Unavailable 선택과 기존 HTTP Fixture Route는 유지합니다.
- 통신 채널은 제한된 크기의 메모리 내 직렬화 데이터이며 공개 Remote Endpoint가 아닙니다. 인터페이스를 구분하며 같은 프로세스의 악성 코드를 격리하지 않습니다. Gateway 재시작·종료 시 임시 Grant가 사라지고 저장된 Lease 만료·복구가 권위 있는 상태로 남습니다. DB/LLM/계정 자격증명을 Mock에 전달하지 않고 Backend는 Execution Request만 받습니다. 운영 TLS·Peer 인증과 전용 Linux Runtime은 M6-B 사전 조건입니다.
- [Linux 사전 점검](linux-runner-preflight.md)은 실제 Darwin/macOS와 Docker VM 메타데이터를 확인하지 못한 VM KVM/Device/권한 동작과 구분합니다. 공식 Firecracker/gVisor/Kernel 요구사항을 향후 호스트 수용 조건에 반영했습니다. 호스트 생성, 가상화·방화벽 변경, Runtime 설치와 Guest 실행은 수행하지 않았습니다.

영문·국문 [Lifecycle](../architecture/judge-lifecycle.md)과 [Runner 명세](../specifications/runner-protocol.md)에 상세 계약을 제공합니다. 기존 API/Framework Request/Result 계약과 원래 채점은 호환되며 Evidence Field는 추가 사항입니다. 보존 정책은 의도적인 데이터 수명주기 변경이며 코드·Schema를 Downgrade해도 정리한 Evidence를 재생성할 수 없습니다.

## 보안 수용과 독립 검토

관찰한 테스트는 정상·동시 Heartbeat, 잘못된 Worker/Attempt/Fence/Token, Capability/Lease/Deadline 만료, DB 시계 차이, 검증 중 만료, Policy/Digest 변조, Replay, 취소·Worker 실패, 오래된 결과 거부, Owner 격리, Runtime Unavailable, 잘못되거나 과도한 Wire/Result, 자격증명 제외, 일회성 Cleanup 결합, 멱등·제한 Cleanup, 실행 중 권한 보호, Quota 회수, Export/삭제, 데이터가 있는 Migration과 Quarantine을 다룹니다. PostgreSQL 갱신·취소·복구·Cleanup·Admission·Result Controller 경쟁은 독립 Connection/Transaction을 사용합니다. 실제 Remote Runner Fleet이나 OS 격리 검증을 의미하지 않습니다.

SECURITY의 적용 범위를 조사·확인하고 제외 범위·심각도 변경·수용 위험 추가 없이 M6-A 불변 조건을 갱신했습니다. 의존성 내부 `expect-type` 정책은 이 소스 경로를 관할하지 않습니다. 관리형 독립 Codex Security Diff Scan `6dfa601d-4bcb-4298-b0e9-43fb9a8b0174`를 봉인하고 재조회했습니다. 결과는 **발견 사항 0개, Surface 20개, Deferred/Exclusions 0개, Coverage Complete**입니다. 관리 도구가 추적한 변경 소스·설정·Script 13개와 추가 설정·Test·Benchmark 7개를 모두 검토했습니다. Inventory SHA-256은 `22aa3a6fe9755f42d48f2547ee14962323e1fcdd1e5e9f7595c931c35337a84c`이며 완료 시 20개 파일 해시가 모두 동일했습니다. 새 아키텍처 Worker는 자원 경계 16개, 해결 질문 8개와 32개 파일의 인용 186개를 확인했습니다. 추가 탐색 Worker의 Thread 제한은 독립 검토자가 보존한 소스 전체를 직접 읽어 보완했습니다. 원래 Snapshot `61b909e7dbdaf7acb878f73d293de9013a833a051ff47e0d66ddc59e355aa3ef`와 이후 문서 변경에 대한 관리 도구 경고를 보존합니다. 이 Scan은 해당 소스 Snapshot을 다루며 최종 문서는 별도로 갱신합니다. 검토자는 애플리케이션 테스트를 실행하지 않았고 Root·구현 측정치를 외부 근거로 구분했습니다. Scanner에서 문제가 나오지 않았다는 사실이 취약점 부재의 증명은 아닙니다. GitHub 자동 Codex 리뷰를 가정하지 않으며 병합 전에 실제 제출된 리뷰와 Thread를 읽어야 합니다.

## Docker, HTTP와 데이터 보존

현재 Compose Image를 Build하고 기존 `praxioj_postgres_data`를 보존하면서 Localhost의 모든 Service가 Healthy 상태가 됐습니다. 추가 Migration을 Volume 초기화 없이 실행했습니다. 기존 M1/M2 HTTP Smoke, Web Proxy를 통과하는 M3, M4 계정·Quota·Export·삭제와 기본 Unavailable Judge Smoke가 통과했습니다. 명시적 Mock Judge HTTP도 실제 API Container 재시작 전후 같은 Pending Job의 영속성, Assessment 수용, Replay·취소 이후 실행 거부, 안전한 Export와 자신이 생성한 합성 계정 삭제를 검증하며 통과했습니다. 원래 Grade와 검증된 Trace는 변하지 않았고 추가 Evidence Status를 검사했습니다. 독립 Maintenance가 성공했으며 애플리케이션 DB의 복구·정리 보고 개수는 모두 0이었습니다. API는 기본 Unavailable 설정으로 되돌렸습니다. 실제 만료 기록을 정리하는 정상 동작은 폐기 가능한 Schema의 테스트·Benchmark로 검증하며 이 0건 통합 실행에서 추론하지 않습니다.

기존 M1–M3 Smoke Script는 설계상 합성 Demonstration 계정을 남깁니다. M4/M5는 자신이 생성한 계정을 제거합니다. PostgreSQL Suite는 자신이 만든 무작위 Schema와 Backup DB만 삭제합니다. 참가자 데이터나 애플리케이션 Volume을 Truncate하지 않습니다. 새 Judge UI·Browser Flow를 검증했다고 주장하지 않습니다. Frontend Source는 바뀌지 않았으며 Frontend Unit/Build와 실제 Web Proxy HTTP 회귀 검증을 실행했습니다.

실제로 실행한 전체 Suite 명령:

```sh
PRAXIOJ_RUN_LIVE_TESTS=0 \
PRAXIOJ_TEST_DATABASE_URL='postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj' \
PRAXIOJ_TEST_BACKUP_CONTAINER=praxioj-db-1 .venv/bin/python -m pytest -q
PRAXIOJ_RUN_LIVE_TESTS=0 PRAXIOJ_TEST_DATABASE_URL= TEST_DATABASE_URL= \
PRAXIOJ_TEST_BACKUP_CONTAINER= .venv/bin/python -m pytest -q
npm --prefix apps/web test -- --run
npm --prefix apps/web run build
.venv/bin/python -m pip check
.venv/bin/python scripts/sync-licenses.py --check
.venv/bin/python scripts/check-docs.py
docker compose -f compose.yaml -f compose.native.yaml up --build -d --wait
```

표시된 DB 자격증명은 저장소의 공개된 로컬 개발 기본값입니다. 추가 실제 HTTP 명령은 기존 `scripts/smoke.py`, `smoke-m2.py`, `smoke-m3.py --base-url http://127.0.0.1:5173`, `smoke-m4.py --base-url http://127.0.0.1:5173`, `smoke-m5.py --expect-unavailable`입니다. 자격증명이 필요한 Provider 테스트를 활성화하지 않았습니다.

## 별도 Optimization & Hardening

구현 후 별도 단계에서 Heartbeat DB 왕복, Row 잠금 순서·경합, Claim 공정성, Cleanup/Index/Batch 비용, 직렬화, 반복 인가, 용량 계산, 실패 복구와 API/AI Worker 분리를 검토했습니다. 보안 검사를 유지하고 검증을 생략하는 신뢰 Flag, 광범위한 Delete, 새 Service나 의존성을 추가하지 않았습니다.

| 작업량과 관찰 | 실제 결과와 해석 |
| --- | --- |
| 제품 수정 전 M5: 고정 Pending/Claimed Fixture 1개, Background AI Worker 없음, 20회 예열 + 7×100 Heartbeat 호출 | 14 SQL/call; 중앙값 6.90287708 ms, 범위 5.98575–8.48312291 ms |
| 동작하는 구현에서 이미 DB로 관찰한 인가 시각을 Source Binding에 재사용하기 전·후, 마지막 갱신 시각은 새로 확인 | SQL 14 → 13/call. 별도 실행 중앙값 5.51311291 → 7.25459458 ms; **지연 개선을 주장하지 않음** |
| 동일 프로세스의 동등한 추가 시계 조회 Reference와 현재 경로, 순서 교대, 경로별 20회 예열 + 7×100 | 14 대 13 SQL/call; 중앙값 5.22951834 대 5.07445458 ms. Reference 범위 4.95826083–7.11807375, 현재 4.93581–5.34921959. 공유 호스트 잡음·범위 중첩과 앞선 반대 결과로 API 지연 개선을 주장할 수 없음 |
| 폐기 가능한 Schema의 현재 Cleanup, Terminal Job 100개와 Live Job 1개 | Payload 단계 685.016459 ms / 1003 SQL / Payload+Attempt 100개 제거; Metadata 단계 501.685292 ms / 1003 SQL / Summary 100개 제거; Live Job 보존, 반복 Cleanup 결과 0 |
| 실제 100행 Retention Selector EXPLAIN | Limit → Index Scan, Planning 0.112 ms / Execution 0.077 ms; 관찰한 계획이며 운영 규모의 보장은 아님 |

같은 로컬 테스트 환경에서 명시적 경로 `.venv/bin/python -m pytest -q -s tests/api/benchmark_judge_lifecycle.py -k paired` 또는 `-k cleanup`으로 개발용 Benchmark를 재현할 수 있습니다. 기본 `test_*.py` 수집에서는 제외됩니다. 교대 측정의 Reference는 같은 버전에서 동등하게 중복 시계를 조회하는 경로이며 이전 Release API를 측정한 것이 아닙니다. M5에는 Purge가 없으므로 Cleanup Before/After 속도 향상을 주장하지 않습니다.

Heartbeat DB 왕복 1회 감소는 관찰한 Query 수로 정당화됩니다. Claim/Source/Owner 검사는 의도된 경계이며 추측에 따른 Cache나 공정성 재설계는 필요하지 않습니다. Cleanup은 맹목적 Bulk Delete 대신 Quarantine·Audit와 짧은 Job별 잠금 Transaction(Job당 10 SQL과 Batch 3개 Statement)을 사용합니다. Runner는 수용한 Heartbeat당 권위 있는 Broker 갱신 1회와 최대 3개 Grant Registry를 사용합니다. 직렬화는 엄격한 크기 제한과 새 검증을 유지합니다. Frontend Polling/Bundle과 의존성은 바뀌지 않았습니다. 측정한 Query 감소 이외의 나머지 경로는 **reviewed; no justified optimization**입니다. 기본 Lease 15초에서 명시적 Dispatch가 실행되는 동안만 5초 주기로 갱신하며 전역 Judge Poller가 추가된 것은 아닙니다.

## 문서와 GitHub 전달

README/CHANGELOG와 한국어 대응 문서는 Unreleased 아래 실제 Lifecycle/Retention/Runner 범위와 안전한 기본값을 설명합니다. 신규 Lifecycle, Runner, Linux 문서는 유지관리 영문·국문 대응 문서와 목차·Manifest 등록을 갖춥니다. 기존 Setup/Data/Backup/Broker 가이드는 범위를 좁혀 갱신하며 상세한 새 정책은 영문·국문 문서에 제공합니다. 관련 없는 과거 문서 전체를 번역하지 않습니다. 루트 보안 지침은 구현된 경계와 일치시킵니다. 로드맵·최종 보고서는 최종 수용 상태에 맞춰 갱신하며 M6-B Open 상태와 Apache-2.0·기여자·제3자 고지를 보존합니다.

Governance PR의 필수 [CI 43688372075](https://github.com/casing1/praxioj/actions/runs/43688372075), [CodeQL 43688372081](https://github.com/casing1/praxioj/actions/runs/43688372081), 추가 [Governance 43688397694](https://github.com/casing1/praxioj/actions/runs/43688397694)가 성공했습니다. CI에서 429 passed/1 skip, Frontend 33과 실제 API 재시작 전후 Pending Judge 영속성을 직접 확인했습니다. 병합 후 main의 CI `43688685676`, CodeQL `43688685679`, Governance `43688685696`도 성공했습니다. PR #28에는 제출된 리뷰·열린 Thread가 없었으며 독립 로컬 소스 검토와 수정은 별도로 공개합니다.

M6-A를 닫기 전에 기능·최종 문서 PR 메타데이터, 필수 검사, 실제 리뷰 결과와 병합 후 Issue/Milestone 상태를 재조회하고 여기에 추가해야 합니다. 객체 생성이나 로컬 테스트만으로 이 단계를 충족하지 않습니다.

## 알려진 한계와 M6-B 종료 작업

실제 격리 Linux/KVM/gVisor 실행, 인증된 Remote Network, 호스트 CPU/Memory/PID/Storage 제한, Filesystem Object 수집, 기본 차단 Egress, Secret Canary 검사, Runtime/Image 출처 수용과 독립 Guest 종료·호스트 복구는 **미구현·미검증**입니다. Docker VM 메타데이터와 합성 Cleanup으로 이 조건을 충족할 수 없습니다. M6-B Issue #23–#27은 열린 상태입니다.

Localhost Preview 제한, 공개 배포 금지, 신뢰된 Host/DB Operator 전제, 운영 Identity Recovery/MFA 미지원, 애플리케이션 Backup 암호화·외부 삭제 Ledger 복제·Restore 승격 미지원은 유지됩니다. 실제 모델 추론, Native Windows, 실제 Remote Network 분할, 대규모 운영 Load/Failover와 OS 격리는 미검증입니다. Maintenance Scheduler가 실패·중단되면 물리적 보존 정리가 늦어집니다. Metadata 상한은 보호된 이력을 일찍 삭제하는 대신 새 작업을 거부할 수 있습니다. 임시 Runner Grant는 재시작 후 Resume를 지원하지 않습니다. 운영용 Sandbox, 정확한 청구 또는 외부 실행의 Exactly-once 보장을 주장하지 않습니다.


추가 민감정보 패턴 검사: 해당 관찰 시점의 작업 트리 텍스트 229개와 도달 가능한 Git Commit 50개의 고유 텍스트 Blob 368개(각 2 MB 이하)에서 일반 비밀정보 패턴 일치가 없었습니다. 값을 출력하지 않았으며, 모든 비밀정보의 부재·도달 불가능한 이력 검사를 보장하거나 GitHub Secret Scanning을 대체하지 않는 휴리스틱 검사입니다.
