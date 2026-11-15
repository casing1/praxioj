# Issue #23 — Linux 호스트·Runtime 사전 점검 검증

[English — canonical source](../../../development/validation-issue23.md) · [문서 목차](../index.md)

## 대상, 범위와 상태

이 기록은 [M6-B — Isolated Linux Runner Validation](https://github.com/casing1/praxioj/milestone/2)의 [Issue #23 — Dedicated Linux host and runtime provenance](https://github.com/casing1/praxioj/issues/23)을 다룹니다. 읽기 전용 환경 관측, 후보 조사, 정적 계약 검토와 문서 산출물의 한계를 기록합니다. [Linux 사전 점검](linux-runner-preflight.md)은 Host Acceptance Matrix, 후보 비교, 최소 권한 요구사항, 미해결 의존성과 구현 순서를 제공합니다.

**실제 Runtime 선정: Blocked.** 유지관리자는 이번 작업에 사용할 전용 Linux 실행 호스트가 없음을 확인했습니다. Firecracker와 gVisor는 **Provisional 후보**이며 실행 승인은 없습니다. 문서는 독립적으로 전달할 수 있지만 실제 필수 호스트 근거가 확보될 때까지 Issue #23과 M6-B는 **Open** 상태를 유지해야 합니다. 이번 작업은 M6-B 격리 수용 조건 A4–A12를 충족하지 않습니다.

제품 Runtime, DB Schema, 실행 계약, 기본 Backend와 의존성은 바뀌지 않습니다. Linux 호스트를 생성하거나 접속하지 않았고 SSH 비밀정보나 전체 프로세스 환경을 검사하지 않았습니다. 이번 로컬 사전 점검에서 `sudo`, Runtime 설치, 후보 Runtime의 VM/Container 작업 실행, 방화벽·가상화 변경, 공개 Listener와 비신뢰 코드 실행을 수행하지 않았습니다. 기본 Judge는 Unavailable이며 Mock 출력은 합성 결과로 유지합니다.

## Revision, 환경과 기준선

사전 점검은 깨끗한 로컬·원격 main `2927336e8c8a25be1a4a5f60002aab0b1e48a9ff`에서 시작했습니다. Issue 연결 브랜치는 `docs/23-linux-runtime-preflight`입니다. 루트 사전 점검에서 열린 PR과 열린 Dependabot·CodeQL·Secret Scanning Alert가 모두 없음을 확인했습니다. 기존 main 보호와 Squash Merge 규칙을 유지합니다. 기존 데이터, 중지된 로컬 Container와 명명된 PostgreSQL Volume을 보존했습니다.

초기 문서 기준선은 **Markdown 66개와 유지관리 번역 Pair 18개**입니다. 수정 전에 로컬 문서 검사, 의존성 일관성과 License Notice 검사가 통과했습니다. 과거 M6-A 전체 Suite 수치를 새 Issue #23 실행으로 보고하지 않습니다. 해당 결과는 [M6-A 보고서](validation-m6a.md)에 별도로 보존합니다.

관측 시각: **2026-11-15T08:16:11Z / 2026-11-15 17:16:11 KST**. Native macOS와 선택한 Docker Desktop 메타데이터만 좁은 범위로 조사했습니다. 임시 관측 JSON은 저장소 밖에 유지하며 원본 호스트 Inventory를 Commit하지 않습니다. 아래 안전한 집계 사실은 원격 호스트를 식별하거나 자격증명을 공개하지 않습니다.

## 관측 사실과 근거의 한계

| 대상 | 실제 관측 | 수용 조건 해석 |
| --- | --- | --- |
| Native OS/Kernel | Darwin `27.0.0`, macOS `27.0.1`, Build `26A434` | macOS 관측이며 전용 Linux 호스트 사전 조건을 충족하지 않음. |
| Native CPU | `arm64`, Apple M2, Logical CPU 8개와 Physical CPU 8개 | Hardware Identity이며 선택한 Linux Runtime·Guest 호환성은 미검증. |
| Native 가상화 메타데이터 | `kern.hv_support=1`, Hypervisor.framework 존재 | Apple Framework 지원은 Linux KVM/API 접근이나 중첩 가상화의 근거가 아님. |
| Native KVM 경로 | `/dev/kvm` 없음, Device Open/Ioctl 시도 없음 | Native macOS 경로만 검사함. Docker VM 내부 KVM·중첩 가상화·예정 Service 계정 접근은 Unknown. |
| Native Identity | 현재 Operator는 Non-root | 생성된 Runner 계정이나 Launcher 최소 권한의 증거가 아님. |
| Native Memory | Physical RAM `17179869184` bytes, `vm_stat`은 16384-byte Page의 Free 수를 4278개로 보고 | 특정 시점의 호스트 상태이며 Free Page는 가용 Memory나 작업별 Admission 보장이 아님. |
| Native Filesystem | 전체 `494384795648` bytes, 가용 `135564394496` bytes, 가용 Inode `1323871040` | 변동하는 로컬 Filesystem 관측이며 전용 호스트 Storage 할당이나 강제 가능한 Job Quota가 아님. |
| Native 실행 파일 검색 | 검사한 PATH에 `firecracker`, `jailer`, `runsc` 없음 | 전체 파일이나 Docker VM을 검색한 것이 아니며 설치된 Runtime 출처를 검증하지 않음. |
| Docker Version/Context | Client/Server `29.4.3`, 선택한 로컬 Desktop Context | 선택한 로컬 Engine 메타데이터이며 원격 Docker 호스트에 접속하지 않음. |
| Docker VM 메타데이터 | Docker Desktop, Kernel `6.12.76-linuxkit`, `aarch64`, CPU 8개, 전체 Memory 보고값 `8321994752` bytes | Engine이 보고한 VM 자원이며 실제 가용·할당 용량이나 승인된 실행 호스트가 아님. |
| Docker 제어 메타데이터 | cgroup v2 / `cgroupfs`, `overlayfs`, 내장 Seccomp·Cgroup Namespace 옵션, Runtime 보고값 `runc`와 `io.containerd.runc.v2` | 실효 Runner Controller 위임, Namespace 격리, LSM 강제나 비신뢰 작업 수용 검증이 아님. |

Docker VM에 들어가지 않았습니다. 기능을 찾기 위한 Privileged Container나 진단 작업을 시작하지 않았습니다. 실제 Controller 위임, Namespace 설정, Seccomp/LSM Profile, Service Identity 권한, KVM 사용 가능성, 중첩 가상화와 Runtime 시작은 통과가 아닌 **Unknown 또는 Not Tested**입니다. 관측 시 로컬 Container는 중지돼 있었고 기존 DB Volume은 존재했습니다. 이번 문서 검증을 위해 로컬 PostgreSQL을 시작하지 않았습니다.

## 후보 조사와 출처 검증 경계

후보 조사에서 다음 Upstream Source 참조를 기록했습니다.

| 후보 | 확인한 Source Pin | 남은 미검증 사항 |
| --- | --- | --- |
| Firecracker | `v1.18.0`, Commit [`eaf83bb718a559d324613d566eaf776b31a62340`](https://github.com/firecracker-microvm/firecracker/commit/eaf83bb718a559d324613d566eaf776b31a62340) | 설치된 Binary, Artifact Digest/Signature, Host/Guest Kernel, Root Filesystem과 호환 전용 호스트를 검증하지 않음. |
| gVisor | `release-20261109.0`, Commit [`a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9`](https://github.com/google/gvisor/commit/a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9) | `runsc` Binary, Artifact Digest/Signature, 선택 Platform, 작업 호환성과 실제 Linux 호스트를 검증하지 않음. |

이 값은 문서·Source Pin이며 배포된 Runtime 출처나 권장 운영 Version이 아닙니다. Binary나 Guest Image를 다운로드·설치·실행하지 않았습니다. Vendor 사전 조건과 Firecracker/gVisor Platform 구분은 [주 사전 점검 문서](linux-runner-preflight.md)의 공식 참조와 함께 설명합니다. 문서에서 보안 순위, 시작 비용, Memory Overhead나 호스트 가용성을 추론하지 않습니다.

## 구현과 통합 검토

문서만 변경합니다. Framework/Platform 분리와 M6-A Broker, Gateway, Capability, Lease/Fencing, Retention, Result Validation 계약을 보존합니다. Backend를 활성화하는 대신 향후 요구사항을 식별합니다.

- 실제 Transport에는 인증되고 별도로 관찰된 Peer Identity를 제공합니다. Message가 스스로 주장한 Identity와 Digest 일치는 인증이 아닙니다.
- API/PostgreSQL/LLM/Session 자격증명을 실행 호스트 Guest Input에 전달하지 않습니다. Runtime별 Launcher, 권한 설정과 Collector는 독립 Framework 및 API/AI Worker 실행 경로 밖에 둡니다.
- 현재 Attempt, Operation, Policy/Input/Image/Request 결합, 만료와 Replay 검사를 유지하며 검증하지 않은 실행을 허용하려고 고정 Mock Protocol을 완화하지 않습니다.
- 논리적 Broker Reservation 해제와 물리 호스트 자원 재사용을 분리합니다. DB Job Terminal, Lease 만료와 합성 Cleanup 응답은 실제 Guest 종료를 입증하지 않습니다. 독립 Watchdog/Reaper와 권위 있는 Cleanup 확인 이후에만 물리 용량을 재사용합니다.
- 불확실한 종료, Host 재시작과 Control Channel 단절은 투명한 재실행 사유가 아닌 복구·Quarantine 의무로 다룹니다. 알 수 없는 Runtime·출처·격리·용량은 실행을 Unavailable로 유지해야 합니다.

최소 호스트 용량은 선언한 Job 예산에 측정한 Runtime/Collector/Watchdog 비용과 검토한 Host 여유분을 더해 결정해야 합니다. 임의의 최소 CPU/RAM/Disk 구매 사양이나 성능 수치를 만들지 않습니다. 문서상의 요구를 충족하려고 권한, Cgroup, Device 접근이나 Host Policy를 변경하지 않았습니다.

## 검증과 실제 결과

| 검사 | 실제 결과와 범위 |
| --- | --- |
| 제한된 Native/Docker 메타데이터 조사 | 위 시각에 읽기 전용 완료, VM 진입·Runtime 시작 없음. |
| 로컬 기준선 문서·의존성·고지 | 기준선 Markdown 66개 / 번역 Pair 18개, 의존성 일관성과 License Notice 동기화 통과. |
| 관련 회귀 검사 | **167 passed, 10 PostgreSQL-only skips, 기존 Starlette 경고 1개; 29.80 s**. 정확한 명령은 아래에 기록하며 전체 PostgreSQL/M6-B Suite가 아닌 관련 로컬 실행임. |
| 정적 계약 Assertion | 현재 Identity/Capability/Provenance/Result/Request Model의 **Assertion 9개 통과**, 상세 내용은 아래에 기록함. OS 격리 실행 없음. |
| Governance 검사기 회귀 | **25 passed; 0.33 s**, `.venv/bin/python -m pytest -q tests/governance`, Skip 없음. |
| Frontend Tests / TypeScript / Vite | **33 passed; 3.27 s**. Build 통과: JS 274.37 kB / gzip 82.90 kB, CSS 31.23 kB / gzip 7.45 kB, Vite 보고값 92 ms. Frontend 동작 변경이나 성능 개선 주장은 없음. |
| 변경 후 문서 링크·번역 Pair | Markdown 68개·등록 번역 Pair 19개 검사 통과. 로컬 대상·Fragment와 상호 Pair를 오프라인으로 확인했으며 의미 검토는 별도. |
| 전용 Linux/KVM/Runtime/OS 수용 | **Blocked / Not Tested**: 승인된 Linux 호스트, Runtime 시작과 격리 시험 없음. |
| 필수 원격 CI/CodeQL/Governance | PR 생성·실제 실행 기록 대기, 로컬 통과에서 추론하지 않음. |

PostgreSQL 테스트 URL을 명시적으로 제외한 관련 회귀 명령:

```sh
env -u PRAXIOJ_TEST_DATABASE_URL -u TEST_DATABASE_URL .venv/bin/python -m pytest -q tests/framework/test_execution_protocol.py tests/framework/test_runner_protocol.py tests/api/test_judge_broker.py tests/api/test_judge_lifecycle.py tests/api/test_judge_runner.py
```

Skip 10개는 Broker의 PostgreSQL Claim/Result, Cancel/Result, Admission 경쟁 3개, Lifecycle의 PostgreSQL 시계·Row Lock Case 6개, Runner 독립 Channel의 Result Commit 경쟁 1개입니다. 로컬 PostgreSQL을 시작하지 않았습니다. Introspection Assertion 9개는 `RunnerIdentity`의 `transport=in_memory_mock`, `synthetic_only=True`, `host_isolation_verified=False`, `BackendCapabilities.untrusted_code_execution=False`, `ExecutionResult.provenance=synthetic_mock`, `SyntheticExecutionAssessment.independent_execution_evidence=False`, Result Model의 `execution_status` 부재·`status` 존재와 `ExecutionInputSnapshot` Request Input Model을 검사했습니다. 정적 계약 근거이며 배포된 설정이나 Sandbox 시험이 아닙니다.

Frontend 실행 기록은 `apps/web`의 `npm test`와 `npm run build`입니다. 기준선 의존성과 고지 실행 기록은 `.venv/bin/python -m pip check`, `.venv/bin/python scripts/sync-licenses.py --check`이며 Markdown·번역 검사기는 `python3 scripts/check-docs.py`입니다. 위의 후보 Source/Version 사실은 별도로 기록한 참고 조사에서 가져왔습니다. 사전 계약 검토와 Model Assertion 9개는 저장소 소스만 확인했고, 이후 독립 Firecracker Source Spot-check는 아래에 기록합니다.

실제·유료 Provider를 사용하지 않았습니다. PostgreSQL 전용 Skip을 보고하며 SQLite가 Row Lock·Worker 경쟁을 검증했다고 주장하지 않습니다. 로컬 Unit·정적 결과는 A4–A12를 충족하지 않습니다. 이번 문서 변경에서 정식 코드 보안 Scan을 수행했다고 주장하지 않습니다. 실제 독립 작업 범위는 읽기 전용 강화·소스 계약 검토입니다.

## 별도 Optimization & Hardening

독립 검토자가 영문 사전 점검, 영문·국문 검증 기록과 변경 경로를 대상으로 문서 작성 후 별도 최적화·강화 검토를 수행했습니다. 정확성 관련 두 사항을 수정했습니다. 최종 수용 전 별도 승인한 통제된 합성 검증만 허용하도록 서비스 활성화 조건을 명확히 했고, 정적 검사 기록에 실제 수행한 Assertion 9개만 정확히 열거했습니다. 검토자는 두 수정을 확인했으며 해당 시점에 남은 차단 사항을 발견하지 않았습니다. 근거 분류, 최소 Launcher 권한, 비밀정보 제외, 기존 합성 계약과 물리 용량 격리 원칙을 유지했습니다. 호스트 수용 시험이나 공식 관리형 보안 Scan은 수행하지 않았습니다. 독립 검토자의 gVisor Spot-fetch에서 Cache Miss가 발생했으므로 해당 Vendor 사실은 주 참조 조사에 근거합니다.

판단은 **reviewed; no justified optimization**입니다. Runtime 경로, 의존성, DB 왕복이나 Launcher를 추가하지 않았습니다. 기존 Broker 계약을 재사용할 수 있고 실제 Transport·격리 제어는 별도 구현·수용이 필요합니다. 후보 Runtime 성능을 측정하지 않았으므로 효율이나 격리 성능 개선을 주장하지 않습니다. 수정 전 문서·테스트 기준선과 수정 후 오프라인 검사는 회귀 범위를 입증하며 속도 비교가 아닙니다.

## Issue #23 수용 조건과 미해결 의존성

| 종료 조건 | 현재 상태 |
| --- | --- |
| 유지관리자가 승인한 전용 Linux 대상·예정 Service Identity | **Blocked**: 유지관리자가 가용 호스트 없음을 확인. |
| 실제 Kernel/CPU/Platform 사전 조건과 필요 시 KVM/API/중첩 가상화를 예정 Identity로 확인 | **Blocked / Unknown**: Native·Engine 메타데이터로 대체할 수 없음. |
| 설치된 Runtime/Launcher/Kernel/Rootfs 출처·Update 담당자 검증 | **Not Tested**: Source Pin만으로 불충분. |
| 최소 권한·자격증명 분리·자원/Cleanup 담당자·후속 순서 문서화 | 문서화한 요구사항이며 적용·검증된 Host Control이 아님. |
| 로컬 문서·정적 회귀 근거 | 명시한 로컬 범위에서 통과, 독립 문서 검토와 정확성 수정 두 건 완료. 호스트 수용 검증은 아님. |
| 실제 보호된 PR 검사·리뷰·메타데이터 확인 | 대기 중. |

**Issue #23 수용 조건은 충족하지 못했습니다.** 문서 전용 PR은 `Refs #23`으로 연결할 수 있지만 병합을 Issue나 M6-B 종료로 이어서는 안 됩니다. Selected 또는 승인된 Runtime은 없습니다. 명시적으로 승인된 지원 호스트가 마련되면 #23의 실제 출처·사전 조건을 해결하고, 의존성에 따라 [#24 격리·자원](https://github.com/casing1/praxioj/issues/24), [#25 네트워크·비밀정보](https://github.com/casing1/praxioj/issues/25), [#26 종료·복구](https://github.com/casing1/praxioj/issues/26), [#27 독립 수용](https://github.com/casing1/praxioj/issues/27)을 구현합니다. 적용되는 OS 수용 조건과 유지관리자 승인을 실제로 충족할 때까지 실제 실행은 Unavailable로 유지합니다.

## GitHub 전달과 최종 상태

기존 [Issue #23](https://github.com/casing1/praxioj/issues/23)과 [Milestone 2](https://github.com/casing1/praxioj/milestone/2)를 재사용하며 중복 관리 객체나 추정 완료일을 만들지 않습니다. 브랜치는 Issue와 연결했습니다. PR URL, 실제 Assignee/Label/Milestone, 필수 검사 링크, 리뷰 결과, 보호 규칙을 따른 Squash 결과와 병합 후 상태는 전달 시 재조회해 기록해야 합니다. 현재 기록에서 PR 검사나 병합을 주장하지 않습니다.

README/CHANGELOG, 주 사전 점검 문서와 목차·번역 등록은 같은 전달 범위에서 검토합니다. Apache-2.0, 기여자·제3자 고지, 데이터 보존과 Localhost 제한은 유지합니다. 해결하지 못한 호스트 사전 조건 때문에 문서 PR 병합 여부와 관계없이 Issue #23과 M6-B는 **Open** 상태입니다.
