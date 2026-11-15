# Linux 호스트와 격리 Runtime 사전 점검 — Issue #23

[English](../../../development/linux-runner-preflight.md) · [문서 목차](../index.md)

## 목적, 범위와 결정

이 문서는 과거 M6-A 사전 점검을 확장한 [Issue #23](https://github.com/casing1/praxioj/issues/23)의 읽기 전용 M6-B 조사다. Maintainer는 이번 작업에 사용할 **전용 Linux 실행 호스트가 없음**을 확인했다. 로컬 조사, 릴리스별 비교, 통합 설계와 문서화는 진행할 수 있지만, 실제 지원 호스트의 수용 검증은 진행할 수 없다.

**운영 Runtime 선정: Blocked. Firecracker: Provisional. gVisor: Provisional. 실행 승인: 부여하지 않음.** 어느 후보도 선정·설치·실행하지 않았다. 네이티브 macOS 실행은 지원되는 Linux 배포 경로가 아니다. 조건부 후보는 향후 평가 대상이며 Backend 활성화 권한이 아니다. 실제 호스트 증거와 종료 조건을 충족할 때까지 Issue #23과 [M6-B](https://github.com/casing1/praxioj/milestone/2)는 Open 상태를 유지한다.

이 변경은 Launcher, 의존성, Transport Listener, Host Policy 또는 실행 가능한 Backend를 추가하지 않는다. Judge 기본값은 Unavailable이며 Mock 출처와 Framework/Platform 분리를 유지한다. 호스트 조사용 VM/Container를 생성하거나 시작하지 않았고, VM에 진입하거나 원격 호스트에 접속하지 않았으며, `sudo`, Runtime 설치, 시스템·방화벽·가상화 설정 변경이나 비신뢰 실행도 수행하지 않았다. 기존 로컬 서비스는 중지 상태를 유지했고 PostgreSQL Volume은 보존했다. 일반 저장소 회귀·CI 테스트는 호스트·Runtime 수용 검증과 별개다.

## 증거 분류

| 상태 | 의미 |
| --- | --- |
| Observed — 관찰됨 | 명시한 읽기 전용 질의가 해당 사실을 반환했다. 해당 관찰 지점과 시각에 한정되며 격리 시험 통과를 뜻하지 않는다. |
| Not satisfied — 미충족 | 필수 Linux 대신 네이티브 Darwin인 경우처럼 현재 환경이 사전 조건을 충족하지 못함을 알고 있다. |
| Unknown — 미상 | Docker VM의 KVM·중첩 가상화·LSM 상태처럼 현재 관찰만으로 해당 속성을 확인할 수 없다. |
| Not Tested — 미시험 | 관련 기능·강제·작업·장애 시험을 수행하지 않았다. |
| Blocked — 진행 차단 | 필요한 대상 접근이나 증거가 없다. 선정·활성화 또는 Issue 종료의 근거가 되지 않는다. |

메타데이터가 관찰되었어도 실제 제어는 Unknown 또는 Not Tested일 수 있다. 이를 Pass로 바꾸지 않는다. 이번 조사로 [격리 제안](../../../architecture/sandbox-architecture.md#threat-to-control-and-acceptance-mapping)의 A4–A12를 통과 처리하지 않는다. 기존 M6-A 프로토콜·Backup 테스트는 자체 범위의 증거이며 새로운 OS 수용 결과가 아니다.

## 현재 관찰 결과

관찰 시각: **2026-11-15 17:16:11 Asia/Seoul** (`2026-11-15T08:16:11Z`). 호스트 목록에는 공개해도 되는 집계 사실만 기록하며 사용자 이름, 일련번호, 자격증명, 원시 Docker 환경이나 비공개 Endpoint 경로를 포함하지 않는다.

| 관찰 지점 | 실제 관찰 | 한계 |
| --- | --- | --- |
| 네이티브 OS·CPU | macOS `27.0.1`, Build `26A434`; Darwin `27.0.0`, `arm64`, Apple M2; 논리·물리 CPU 각각 8개 | 네이티브 호스트는 Linux가 아니다. 아키텍처만으로 Runtime·작업 호환성을 입증하지 않는다. |
| 가상화 메타데이터 | `kern.hv_support=1`; Hypervisor.framework 존재; `hw.optional.arm64=1` | 네이티브 지원 표시는 사용 가능한 Linux KVM API, Docker VM 중첩 가상화 또는 권한 시험이 아니다. |
| 네이티브 KVM·Runtime 검색 | `/dev/kvm` 없음; 검색한 네이티브 PATH에 `firecracker`, `jailer`, `runsc` 없음 | Device Open/ioctl, Binary 실행 또는 전체 파일시스템 검색을 수행하지 않았다. Docker VM 상태는 Unknown이다. |
| 운영자 신원 | 현재 네이티브 Process는 root가 아님 | 전용 Linux Runner 계정이나 권한 하향의 증거가 아니다. Docker 제어 권한은 별개다. |
| 네이티브 자원 | 물리 RAM `17179869184` Bytes; 디스크 전체 `494384795648`, 가용 `135564394496` Bytes; 파일시스템 가용 Inode `1323871040`개 | 공유 네이티브 파일시스템·메모리의 순간 관찰이며 예약된 Linux Guest 용량이나 강제된 Quota가 아니다. |
| 네이티브 메모리 Snapshot | `vm_stat`: Free Page 4,278개, Page당 16,384 Bytes | Free Page만으로 회수 가능·압축·비활성 메모리 효과를 반영할 수 없다. 신뢰할 수 있는 Runner 수용 예산을 추론하지 않는다. |
| Docker Context | 기존 `desktop-linux` 선택; 목록의 Context 2개는 로컬 Unix Endpoint 사용; `DOCKER_HOST` 재정의 없음 | 원격 실행 호스트를 식별하거나 접속하지 않았다. Endpoint 경로는 생략했다. |
| Docker 버전 | Client/Server `29.4.3` | 버전 출력은 격리를 인증하지 않는다. |
| Engine VM 메타데이터 | Docker Desktop; LinuxKit `6.12.76-linuxkit`, `aarch64`; CPU 8개, 보고된 메모리 `8321994752` Bytes | Engine이 보고한 VM 총량이다. 실제 VM의 가용 디스크·메모리나 전용 호스트 적합성은 측정하지 않았다. |
| Engine 기능 | cgroup v2, `cgroupfs`, `overlayfs`; Security Option에 기본 seccomp와 `cgroupns` 표시 | Controller 위임·유효 제한, Namespace 동작, seccomp 거부 또는 활성 LSM Profile을 시험하지 않았다. |
| Engine Runtime 목록 | `runc`, `io.containerd.runc.v2` 보고; 기본값 `runc` | 승인된 Firecracker/gVisor Runtime이 표시되지 않는다. VM 전체 파일 검색이나 Sandbox 승인이 아니다. |

재현 가능한 읽기 전용 질의 종류는 `uname -srm`, `sw_vers`, 기록한 하드웨어 Flag·개수에 대한 `sysctl -n`, `vm_stat`, `statvfs`·디스크 사용량, 네이티브 PATH 검색과 선택한 로컬 Docker Context·Version·Info 필드 조회다. Docker 출력은 기록 전에 필터링했다. 확장된 `compose config`, 원시 `docker inspect`·환경, 비공개 연결 정보나 자격증명을 공개하지 않는다. 질의는 설치, KVM Open/ioctl, Namespace 생성 또는 강제 시험을 수행하지 않았다. 영구 수집 도구는 추가하지 않는다. 이 제한된 운영자 관찰만으로 새 Runtime 의존성이나 범용 원격 Probe를 정당화할 수 없다.

## Linux 호스트 수용 Matrix

| 평가 항목 | 현재 증거·상태 | 승인된 전용 Linux 대상에서 필요한 증거 |
| --- | --- | --- |
| 대상 신원·소유권 | Blocked: Maintainer가 전용 호스트 부재 확인 | 승인된 대상과 운영자, 관찰 시각, 예정 서비스 신원과 허용된 비파괴 조사 범위 |
| OS·Kernel·아키텍처 | 네이티브 Darwin: Not satisfied; Docker Linux 메타데이터: Observed만 해당 | 선정한 릴리스·Platform Matrix와 일치하는 정확한 배포판·Kernel·Config·Page Size·CPU 아키텍처 |
| CPU 가상화 | 네이티브 지원 Flag: Observed; Linux 기능: Unknown | 예정 신원에서 실제 관련 CPU·Kernel Interface 확인. Processor Model이나 제품 지원 표시만으로 충분하지 않다. |
| KVM Device·접근·API | 네이티브 경로 없음; 대상 Unknown/Blocked | 필요한 경우 Device Type·권한과 승인된 API Version 질의. #23에서는 VM을 생성하지 않는다. Device 존재나 접근 Bit만으로 기능을 입증하지 않는다. |
| 중첩 가상화 | Unknown | 대상의 가상화 여부와 선택한 Runtime의 요구 기능 가용성 확인. 적용 가능한 Platform을 입증한 경우에만 Not Applicable로 판단하며 가정으로 처리하지 않는다. |
| cgroup v2 | Docker 메타데이터 Observed; 유효 제어 Unknown | 가용·위임 CPU·Memory·PID·관련 I/O Controller, 실제 하위 트리 배치와 상위 제한. 강제 시험은 #24 범위다. |
| Namespace 지원 | Docker `cgroupns` 메타데이터만 관찰; 그 외 유효 분리 Unknown | Kernel 지원, 서비스 권한과 제안된 Mount·PID·IPC·User·Network 분리. 실제 격리는 Not Tested다. |
| Seccomp·LSM | Engine 기본 seccomp 표기 Observed; 유효 Filter·LSM Unknown | 선택한 Runtime의 System Call Filter 요구사항과 활성 LSM·Profile Policy. 안전하지 않은 구성의 거부도 포함한다. |
| 전용 계정·권한 | 현재 네이티브 비root 운영자만 확인; 대상 Blocked | 전용 신원, 정확한 Launcher 설정·권한 하향 모델, Device·Controller 권한과 검토된 권한 범위. 포괄적인 root·Privileged 대체 경로는 허용하지 않는다. |
| Runtime 설치·출처 | 네이티브 PATH·Engine 목록만 확인; 대상 Blocked | 아키텍처별 Runtime과 동반 Artifact, 승인된 출처·버전·Digest, 검증과 갱신 책임자 |
| Kernel·Image·Root Filesystem | 대상 Artifact 없음; Blocked | 승인된 Host·Guest Kernel과 Config, 불변 Rootfs·OCI Digest, Builder·Source·License·SBOM과 적용할 서명·Attestation Policy |
| 디스크·메모리·여유 용량 | 네이티브 Snapshot과 Engine 총량만 확인; 대상 Blocked | 실제 대상의 가용 메모리·스토리지·Inode, 전체 작업 예산, 실측 Runtime·Collector·Reaper Overhead, Host Reserve와 수용 계획 |
| 유효 파일시스템·네트워크·자원 제어 | Not Tested | 실제 선정 구성에서 #24·#25의 합성 정상·거부 시험. 표기나 Flag는 증거가 아니다. |
| Cleanup·장애·복구 | Not Tested | #26의 독립 Watchdog·Reaper와 할당 상태 대조, 이후 #27의 실제 장애·격리 수용 검증 |

## 버전별 자료와 출처 검증의 한계

2026-11-15 공식 자료를 확인했다. 후보 기준은 **Firecracker v1.18.0**, Source Commit `eaf83bb718a559d324613d566eaf776b31a62340`과 **gVisor release-20261109.0**, Commit `a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9`다. 이는 Source 문서의 고정 리비전이며 검증된 실행 파일·Guest Kernel·Rootfs 또는 설치 호스트의 Digest가 아니다. Release·Checksum 메타데이터만 읽었고 Runtime Artifact를 내려받거나 설치·Hash 계산·실행·서명·Attestation 검증하지 않았다. 향후 채택 전에 고정 버전과 보안 공지를 다시 평가한다. [FC Release][fc-release], [gVisor Release][gv-release].

평가한 Firecracker 배포는 일반 Linux/KVM 경로다. 고정한 Kernel Policy는 4 KiB Host·Guest Kernel 계열 5.10, 6.1, 6.18을 열거한다. 관찰한 Docker LinuxKit 6.12는 목록에 없다. 이는 수용 결과도, 비호환성을 입증한 실험도 아니다. v1.18.0은 Nitro 대안도 도입하지만 별도 인프라와 검토가 필요하며 여기서 KVM 부재를 자동 대체하지 않는다. [요구사항][fc-start], [Kernel Policy][fc-kernel], [Release][fc-release].

고정한 gVisor 설치 지침은 Linux 5.6+와 x86_64/ARM64를 열거하며 Package에는 `runsc`와 함께 `gvisor-bin/` 동반 파일이 포함된다. 실제 대상에는 복사한 Binary 하나나 범용 Rootless 표기만이 아니라 완전한 아키텍처별 Artifact와 선택한 Platform의 요구사항이 필요하다. [설치][gv-install], [Platform][gv-platform].

## Runtime 후보 비교

다음 Vendor 설명은 요구사항·설계 입력이며 관찰된 PraxiOJ 격리나 성능이 아니다.

| 평가 항목 | Firecracker v1.18.0 | gVisor release-20261109.0 |
| --- | --- | --- |
| Host Requirements — 호스트 요구사항 | 평가한 일반 경로: 서비스 신원에서 기능하는 Linux·KVM, 지원 Kernel·Config·Page Size Matrix | Linux 5.6+와 호환되는 선택 `systrap` Platform; KVM Platform은 사용 가능한 KVM도 필요 |
| Architecture Compatibility — 아키텍처 호환성 | x86_64/aarch64; 정확한 Runtime·Host/Guest Kernel·작업 조합은 미검증 | x86_64/ARM64; 정확한 Platform·Runtime Artifact·작업 조합은 미검증 |
| Isolation Boundary — 격리 경계 | MicroVM별 별도 Guest Linux, VMM/KVM과 Host 제어 | Sentry의 Userspace Linux ABI 경계; KVM Platform도 완전한 Guest Linux VM이 아닌 Process Model 유지 |
| Required Privileges — 필요 권한 | 권한 있는 jailer 설정 후 전용 UID/GID 사용; 정확한 최소 설정 권한 검토 필요 | OCI·User Namespace·Mount·Network·cgroup 경로에 따라 달라짐; Rootless만으로 충분한 증거가 아님 |
| Filesystem Isolation — 파일시스템 격리 | 승인된 Kernel·Rootfs·Block Backing과 제한된 jailer 트리; Host 노출을 명시적으로 제한해야 함 | OCI Rootfs·Mount 권한, Gofer와 선택한 directfs 동작; 안전하지 않은 Host Mount 거부 |
| Network Isolation — 네트워크 격리 | TAP·Namespace와 외부 Host Filter; VMM만으로 Traffic Filter를 제공하지 않음 | Netstack 구성; `--network=none`에서도 내부 Loopback 유지; Host Network는 제안한 Policy 범위 밖 |
| Resource Enforcement — 자원 강제 | VM Sizing, 유효 Host cgroup·rlimit와 독립 Deadline·Output 제어 | Sentry·작업 메모리를 포함하는 유효 Host cgroup; Host PID 수는 내부 Task 수와 다름 |
| Operational Complexity — 운영 복잡성 | Kernel·Rootfs·Jail·Network·cgroup·VMM·Orphan 수명주기 | OCI Bundle·Runtime 동반 파일·Sentry/Gofer·Mount/cgroup·Orphan 수명주기; 비용 순위를 측정하지 않음 |
| Verified Environment — 검증 환경 | Runtime·Guest 실행 없음; 네이티브·Docker 메타데이터만 관찰 | `runsc`·작업 실행 없음; 네이티브·Docker 메타데이터만 관찰 |
| Unverified Requirements — 미검증 요구사항 | 전용 Host·KVM·권한·출처·Policy 강제·작업 호환성·장애·Cleanup | 전용 Host·Platform·seccomp/OCI/위임·System Call/작업 호환성·출처·장애·Cleanup |

출처: [FC 설계][fc-design], [jailer][fc-jailer], [Host 설정][fc-host]; [gVisor Platform][gv-platform], [파일시스템][gv-fs], [네트워크][gv-net], [자원][gv-resources], [Rootless][gv-rootless]. 어느 경계도 Orchestration·Kernel·Collector·설정 위험을 제거하지 않는다.

### 선정 전 후보별 확인 사항

- Firecracker: 실제 jailer·VMM 신원, System Call Policy와 유효 cgroup 소속을 검증한다. 요청한 cgroup 경로만으로 배치를 입증할 수 없다. 호출자가 책임지는 Orphan·Reaper 로직은 실제 VMM을 처리해야 하며 jailer PID 또는 협조적 Shutdown이 VMM을 종료한다고 가정하지 않는다. 정확한 Launcher 권한 모델 검토는 미해결이다. [Jailer][fc-jailer], [운영 Host 설정][fc-host].
- gVisor: 정확한 시작 경로를 선택한다. 고정 버전의 내장 `--rootless` 경로에는 수명주기·네트워크 제한이 있고 cgroup 설정 오류를 무시할 수 있다. 네이티브 OCI Rootless 경로는 Namespace 한계가 다르다. 필요한 Network·Controller 동작을 입증하지 않고 어느 쪽도 권장하지 않는다. 운영 지침은 이번 비신뢰 코드 용도를 위한 완전한 안내서가 아니다. [Rootless][gv-rootless], [운영 지침 범위][gv-prod].
- gVisor: 파일시스템·directfs와 Network Mode를 명시적으로 선택한다. 호환성 우회책으로 Host Network나 신뢰된 Mount 자원을 사용하지 않는다. Compiler/JIT, Fork·Thread, Signal, mmap, 동적 로딩·Native Extension과 File I/O는 예정한 Judge 언어·Toolchain의 정확한 작업 시험이 필요하다. Upstream Application 예제는 PraxiOJ 호환성을 입증하지 않는다. [파일시스템][gv-fs], [네트워크][gv-net], [호환성][gv-compat].
- 공통: Cleanup 지연, 시작 시간, 메모리 Overhead, 지원 작업 범위, 실제 격리와 Host 가용성은 **Not Tested**다. 보안 강도·비용·속도 순위를 측정하지 않았다.

### 선정 규칙

1. 승인된 전용 Linux 대상과 출처 증거를 확보할 때까지 Blocked를 유지한다.
2. 실제 KVM·아키텍처·Kernel·신원 사전 조건이 고정한 Firecracker 경로와 일치하면 별도로 승인된 안전한 작업으로 해당 후보를 먼저 평가한다. 버전 문자열, CPU 이름이나 Device 목록만으로 선정하지 않는다.
3. 해당 경로가 사전 조건을 충족할 수 없으면 적절한 경우 `systrap`을 포함해 지원되는 gVisor Platform을 평가한다. KVM 부재가 gVisor 적합성을 자동 입증하지 않는다.
4. 지원 호스트 증거를 검토한 뒤에만 선정한다. 선정해도 비신뢰 실행 권한을 부여하지 않는다. #24–#27과 A4–A12 수용 검증은 별도 Gate다. 네이티브 macOS, 일반 Container 또는 다른 Runtime으로 대체하지 않는다.

## 필요한 Host 구성과 출처 관리

다음은 향후 요구사항이며 #23에서 적용한 변경이 아니다.

| 요구사항 | 필요한 구체적 기록·강제 책임 |
| --- | --- |
| 전용 Host·신원 | 승인된 폐기 가능한 실행 대상, 전용 서비스 계정, API·AI Worker 신원 공유 금지. 운영자는 정확한 설정·권한 하향 범위와 Patch 책임을 기록한다. |
| 자격증명 분리 | Guest 환경·파일·proc·출력에 PostgreSQL·LLM·Account/Session/CSRF·Cloud·Agent 자격증명을 전달하지 않는다. Supervisor에는 제한된 Control Channel 권한만 부여한다. #25·#27의 합성 Canary로 입증한다. |
| 최소 Launcher 권한 | 고정·승인 Runtime·Image 식별자와 제한된 Policy 값. 호출자의 Host Path·Flag·Shell을 받지 않는다. 필요한 Device·Mount·Controller·Namespace 작업을 열거하고 작업 전에 권한 하향을 검증한다. |
| 출처 Manifest | Runtime·jailer 또는 Runtime 동반 파일, Host와 필요한 Guest Kernel·Config, Rootfs·OCI Image와 승인 Toolchain에 대해 버전·아키텍처·출처/Build Recipe·불변 Artifact Digest·검증 Policy/결과·License/SBOM·담당자·갱신/폐기 절차를 기록한다. |
| 파일시스템·네트워크 | 승인된 Read-only Root·Input, 새 제한 Scratch·Output. Host Home·Repository·DB·Backup·Runtime Socket Mount 금지. Guest의 외부·Host·Peer Traffic을 기본 차단하고 Proxy를 상속하지 않는다. 실제 IPv4/IPv6/DNS/TCP/UDP 동작을 검증한다. |
| 자원 Sizing | Attempt별 CPU·경과 시간·Memory/Swap·PID·Storage/Inode·Output·Collector 예산을 정의한다. 실측 VMM/Sentry/Gofer/Launcher/Collector/Watchdog Overhead와 Host 여유 용량을 예약한다. 동시성을 늘리기 전에 Controller 상위 계층과 전체 제한을 검증한다. |
| Cleanup | 독립 Watchdog·Reaper와 영속적인 할당 신원·Generation. Cleanup이 불확실하면 용량을 격리한다. 제한된 출력 수집과 Host 재시작 상태 대조 후에 재사용한다. |

**실측한 하드웨어 구매 최소 사양은 없다.** 수용할 Job 예산, 실측 Runtime·지원 구성요소 Overhead와 Host Reserve로 대상 용량을 산정한다. 현재 Mac·Docker 총량은 해당 용량을 입증하지 않는다. 전용 지원 Linux 호스트는 필요한 가상화·중첩 가상화·권한·Runtime 호환성을 입증한 뒤에만 Bare Metal 또는 적합한 VM이 될 수 있다. 이번 작업은 대상을 Provision하거나 구매하지 않는다.

## M6-A 통합 평가

| 통합 영역 | 재사용 가능한 현재 제어 | 추가로 검토할 Interface·미해결 사전 조건 |
| --- | --- | --- |
| 별도 Host 신원 | 생성자에서 관찰한 Mock 신원, 고정 Worker·Attempt | 인증한 Peer 검증과 승인 Host/Runtime Registry가 제공하는 등록·폐기 가능한 서비스 신원. Payload 이름을 신원으로 사용하지 않는다. |
| 인증된 Channel | 크기가 제한된 In-memory 버전별 Wire Message; Runner Listener 없음 | 암호화와 Peer 인증을 갖춘 Transport, 제한된 I/O·협상·Timeout, Provisioning·폐기와 재접속·Receipt 의미 |
| Job별 권한 | 비공개 Broker Lease; Hash로 보관하는 제한된 Operation Grant 3개, 교체와 Fence·Digest 검사 | 승인된 Host·할당 Generation에 결합. Artifact·Status 권한 명시. 원본 Broker Lease와 Channel Grant는 Guest 밖에 보관한다. |
| State·Heartbeat | DB가 권위 있는 갱신·만료를 결정하고, Local Loop 종료를 기다림 | 인증된 관찰과 권위 있는 상태를 구분. Replay를 허용하지 않는 원격 ACK 유실 복구. Host Local의 독립 Deadline |
| 만료·취소 | Terminal Fence·권한 폐기와 오래된 결과 거부; 영속화된 Owner 취소 확인 | DB Job의 취소·만료만으로 실제 Guest가 멈추지 않는다. 분할·장애 상황에서도 독립적으로 Signal·Kill·Reap·상태 대조를 수행한다. |
| Artifact·결과 | 엄격한 M5 상관관계, Inline UTF-8 크기·Hash·경로·Criterion과 64 KiB Envelope 검사 | 실제 일반 파일을 다루는 제한된 신뢰 Collector, Descriptor·Type·Link·Race 검사. Binary·대용량 Channel은 명시적으로 버전 관리하며 임의 URL·Host Path를 허용하지 않는다. |
| 비밀정보 | Backend에는 Request만 전달; Gateway가 Broker·Settings·DB 권한 보유 | 실행 서비스·Guest 신원 분리. Platform Network·Mount·Credential 상속 금지. 실제 작업 연결 전 Canary 증거 확보 |
| Host 장애·Cleanup | 일시적인 Channel 종료와 영속 Lease 복구; DB 이력 보존 | 영속적인 물리 할당·Cleanup State, 독립 Reaper·Orphan 상태 대조와 격리. 해체를 검증한 뒤에만 물리 용량 반환 |

현재 Terminalization은 **논리 Output 예약**을 반환한다. 실제 Host 용량 재사용을 승인할 수 없다. 현재 Stop-and-wait Heartbeat Grant 교체와 결과 하나를 받은 뒤의 Channel 종료에도, 다른 Transport를 설계하기 전에 원격 ACK·Receipt 유실 처리가 명시되어야 한다. 여기서는 해당 Interface를 추가하지 않는다. Source 경로: `apps/api/src/praxioj_api/judge.py`, `judge_runner.py`, `judge_routes.py`; Framework `execution/runner.py`, `execution/protocol.py`, `evaluation/execution.py`.

`in_memory_mock`, `synthetic_only=true`, `host_isolation_verified=false`, `provenance=synthetic_mock`, `independent_execution_evidence=false`를 유지한다. 현재 Validator는 `not_required/synthetic_no_resources` Cleanup과 실측 자원 사용량 부재를 요구한다. Request·Cleanup Model의 향후 용도 Enum 이름이 실행을 구현한 것은 아니다. 현재 `execution_status` 필드는 없다. `ExecutionResult.status`와 `JudgeJob.state`는 서로 다른 기존 의미를 유지한다. 실제 실행은 Mock 주장을 넓히거나 이름을 바꾸는 대신 별도로 검토·버전 관리한 계약과 검증이 필요하다. [Runner 계약](../specifications/runner-protocol.md), [수명주기](../architecture/judge-lifecycle.md).

## 미해결 의존성과 M6-B 순서

| 단계 | 사전 조건·산출물 | 현재 상태 |
| --- | --- | --- |
| #23 Host·Runtime 사전 점검 | 승인된 실제 대상·서비스 신원 목록, 일치하는 후보 요구사항과 Artifact 출처. 검토한 Host Manifest 유지 | 실제 Host 수용 검증은 Blocked. 로컬 조사·설계·문서는 `Refs #23`으로 병합 가능 |
| #24 자원·파일시스템 제어 | 선정 Host 증거 확보 후, 별도로 승인한 합성 작업으로 고정·승인 Launcher Policy, Host 예약·제한과 제한된 Collector 구현 | 미구현 / Not Tested |
| #25 네트워크·비밀정보 분리 | 서비스·작업 연결 전에 실제 차단 Policy, Platform 권한 비상속과 합성 Canary·Probe 계획 수립 | 미구현 / Not Tested |
| #26 Watchdog·Cleanup·통합 | 독립 Kill·Reap·Orphan·Host 재시작 상태 대조와 물리 용량 격리. 활성화 전에 인증 Transport·Receipt 작업 책임을 명시 | 미구현 / Not Tested |
| #27 독립 수용 검증 | 실제 지원 Host 구성과 A4–A12 전반의 정상·거부·장애·공격적 시험 증거, 검토한 Finding과 잔여 한계 | 미구현 / Not Tested |

선정 후 #24·#25 설계 준비를 진행할 수 있지만, 필요한 Cleanup과 독립 수용 검증 전에 참가자 대상 서비스나 비신뢰 코드 실행 서비스를 활성화하지 않는다. 그 이전의 통제된 합성 검증 작업은 별도의 명시적 승인과 적용 가능한 안전 제어가 필요하며 이번 #23 작업은 이를 승인하지 않는다. 이 순서는 중복 Issue를 만들거나 구현 범위를 조용히 넓히지 않는다. 후속 작업 전에 기존 Issue에서 구체적인 Interface 책임을 확인한다. Host 접근, Policy 적용, 설치, Provisioning과 실행은 별도 승인이 필요하다.

## 검증, 최적화와 참고

[Issue #23 검증](validation-issue23.md)은 실제 관찰, 정적 계약 검사, 회귀 테스트, CI·CodeQL과 전달 결과를 기록한다. Mock·SQLite·CI 성공은 없는 Linux 대상의 적합성을 인증하거나 Issue #23·M6-B 수용 상태를 바꾸지 않는다. [M6-A 보고서](validation-m6a.md)는 과거 구현 증거로 유지한다. [SECURITY](../../../../SECURITY.md)와 [격리 제안](../../../architecture/sandbox-architecture.md)의 현재 경계도 유지한다.

**Reviewed; no justified optimization.** Runtime 코드, Probe Service, 의존성이나 중복 실행 계약을 추가하지 않는다. 기존 Broker 제어를 재사용하고 실제 Host 요구사항을 확인한 뒤에만 향후 Interface를 추가한다. 시작·Cleanup·Overhead 또는 보안·성능 개선을 측정하지 않았다. 별도의 문서 작성 후 Hardening 검토는 최소 권한, 증거 분류, 기본값 유지와 정확한 Blocked Gate를 확인하며 실제 결과는 검증 기록에 남긴다.

### 고정한 공식 자료

[fc-release]: https://github.com/firecracker-microvm/firecracker/releases/tag/v1.18.0
[fc-start]: https://github.com/firecracker-microvm/firecracker/blob/eaf83bb718a559d324613d566eaf776b31a62340/docs/getting-started.md
[fc-kernel]: https://github.com/firecracker-microvm/firecracker/blob/eaf83bb718a559d324613d566eaf776b31a62340/docs/kernel-policy.md
[fc-design]: https://github.com/firecracker-microvm/firecracker/blob/eaf83bb718a559d324613d566eaf776b31a62340/docs/design.md
[fc-jailer]: https://github.com/firecracker-microvm/firecracker/blob/eaf83bb718a559d324613d566eaf776b31a62340/docs/jailer.md
[fc-host]: https://github.com/firecracker-microvm/firecracker/blob/eaf83bb718a559d324613d566eaf776b31a62340/docs/prod-host-setup.md
[gv-release]: https://github.com/google/gvisor/releases/tag/release-20261109.0
[gv-install]: https://github.com/google/gvisor/blob/a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9/g3doc/user_guide/install.md
[gv-platform]: https://github.com/google/gvisor/blob/a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9/g3doc/architecture_guide/platforms.md
[gv-fs]: https://github.com/google/gvisor/blob/a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9/g3doc/user_guide/filesystem.md
[gv-net]: https://github.com/google/gvisor/blob/a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9/g3doc/user_guide/networking.md
[gv-resources]: https://github.com/google/gvisor/blob/a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9/g3doc/architecture_guide/resources.md
[gv-rootless]: https://github.com/google/gvisor/blob/a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9/g3doc/user_guide/rootless.md
[gv-prod]: https://github.com/google/gvisor/blob/a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9/g3doc/user_guide/production.md
[gv-compat]: https://github.com/google/gvisor/blob/a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9/g3doc/user_guide/compatibility.md

자료는 재현성을 위해 고정했으며 설치 Artifact의 진위를 입증하지 않는다. 채택 전에 실제 대상에서 선정 Release의 전체 Artifact, 보안 공지, Source·Build와 갱신 Policy를 검증한다. 일반 [Linux cgroup v2 명세](https://docs.kernel.org/admin-guide/cgroup-v2.html)는 계층·위임을 설명하지만 읽는 것만으로 로컬 강제를 입증하지 않는다.
