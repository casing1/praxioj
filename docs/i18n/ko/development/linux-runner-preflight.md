# Linux Runner 호환성·격리 사전 점검

[English](../../../development/linux-runner-preflight.md) · [문서 목차](../index.md)

## 개요와 상태

M6-A [Issue #20](https://github.com/casing1/praxioj/issues/20)의 조사로 현재 개발 호스트 관찰, 공식 Runtime 사전 요구사항과 향후 전용 Linux 실행 호스트에 필요한 증거를 기록한다. 실행하지 않는 사전 점검이며 격리 Runner의 승인이 아니다. 전용 Linux 호스트에 접근하거나 Runtime을 설치하지 않았고 운영체제·방화벽·가상화 설정도 바꾸지 않았다.

PraxiOJ는 실제 비신뢰 코드 실행이 Unavailable인 localhost 개발 미리보기다. M6-A 수명주기·합성 통신 테스트는 [격리 설계](../../../architecture/sandbox-architecture.md)의 OS 수용 기준을 통과시키지 못한다. 실제 격리 실행은 별도의 Open [M6-B](https://github.com/casing1/praxioj/milestone/2) 범위다.

## 범위와 비목표

커널·아키텍처, KVM, 후보 Runtime, Namespace·cgroup, 파일시스템·네트워크 경계, 출처, 권한, 할당량과 독립 Cleanup을 조사한다. 독립 Framework/Platform 경계와 기존 계약을 유지한다. VM 생성, 운영 Runtime 선정, Firecracker/gVisor 설치, Guest·Container 작업 실행, 참가자·Evaluator 코드 실행, Linux 설정 변경이나 공개 Runner Endpoint 승인은 수행하지 않는다.

## 관찰한 개발 환경

**2026-11-15 (Asia/Seoul)** 읽기 전용으로 조사했다. 해당 개발 환경의 관찰이며 지원 호스트 인증이 아니다.

| 항목 | 실제 관찰 | 입증하지 않는 사항 |
| --- | --- | --- |
| 네이티브 호스트 | `uname`: Darwin `27.0.0`, `arm64`; `sw_vers`: macOS `27.0.1`, Build `26A434`; `hw.optional.arm64=1` | 네이티브 Linux Kernel, Namespace·cgroup 강제나 사용 가능한 KVM을 검증하지 않았다. |
| Docker Client/Server | 둘 다 `29.4.3` | Docker 버전은 격리 수용 결과가 아니다. |
| Docker Engine 환경 | `Docker Desktop`, Kernel `6.12.76-linuxkit`, `aarch64`, CPU 8개, 총 Memory `8321994752` Bytes | Engine이 보고한 VM 자원이며 Job별 할당량이나 가용 용량 보장이 아니다. |
| Engine 제어 메타데이터 | cgroup v2, `cgroupfs`; Security Option에 기본 seccomp와 cgroup Namespace 지원 표시 | 향후 Runner의 실제 설정이나 자원·탈출·Egress 강제를 보여주지 않는다. |
| 네이티브 KVM 경로 | macOS 호스트에 `/dev/kvm` 없음 | Docker VM 내부의 KVM, 중첩 가상화, Device 접근, ioctl 동작과 권한은 **미상**이다. macOS 경로 부재로 VM 상태를 판단하지 않는다. |
| 네이티브 실행 파일 검색 | 호스트 명령 검색 경로에 `firecracker`, `jailer`, `runsc` 없음 | 검색한 호스트 PATH의 결과이며 VM이나 모든 호스트 파일에 대한 조사가 아니다. |

Docker VM에 들어가 Runtime·KVM을 검사하지 않았다. 작동하는 Firecracker/gVisor 설치의 증거도, 일반 Docker Container를 보안 Sandbox로 승인할 증거도 없다. 호스트 Subprocess나 Container로 대체하여 이 macOS 환경이 전용 Linux/KVM 배포 계약을 충족한다고 취급할 수 없다.

## 후보 Runtime 사전 요구사항

제안한 Firecracker 경로는 **전용 Linux/KVM 호스트**다. 공식 시작 문서는 이 경로에 x86_64/aarch64 Linux와 `/dev/kvm` 읽기·쓰기 접근을 설명한다. 채택 전에 선택한 릴리스의 지원 Kernel 목록을 고정하고 서비스 신원으로 실제 Device·API를 검증해야 한다. 다른 Vendor 배포 방식은 이번 제안에 포함하지 않는다. [Firecracker 사전 요구사항](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md).

Firecracker 운영 지침에는 Host·Guest 구성요소 패치, 제한적인 seccomp와 jailer에 준하는 제약, Guest 제어 출력의 Host 제한이 포함된다. Quickstart Boot만으로 수용 기준이 충족되지는 않는다. [Firecracker 운영 호스트 지침](https://github.com/firecracker-microvm/firecracker/blob/main/docs/prod-host-setup.md).

gVisor 설치 문서는 현재 Linux 5.6+와 x86_64/ARM64를 지원 대상으로 제시한다. Platform 지침은 KVM과 `systrap`을 구분한다. 모든 gVisor 설정에 KVM이 필요하다거나 아키텍처 지원이 애플리케이션 호환성을 입증한다고 추론하지 않는다. 선택한 Platform·버전에 대한 작업·권한·격리 시험이 필요하다. [설치](https://gvisor.dev/docs/user_guide/install/), [Platform 지침](https://gvisor.dev/docs/architecture_guide/platforms/).

Vendor 사전 조건은 조사 입력이며 PraxiOJ 보안 보장이나 실측 성능 비교가 아니다. 지원되는 KVM 호스트에서 Firecracker를 먼저 평가하고 gVisor를 별도 검증 대안으로 평가하는 방식은 제안이다. 여기서 후보를 설치하거나 승인하지 않았다.

## Linux 수용에 필요한 증거

다음은 **M6-B의 PraxiOJ 요구사항**이며 관찰한 제어가 아니다. 누락·미지원 항목이 있으면 실제 실행을 Unavailable로 유지한다.

| 영역 | 전용 호스트에서 확보할 증거 | 담당·추적 |
| --- | --- | --- |
| Kernel·CPU | 배포판·Kernel Build, 아키텍처, 패치 정책, 선택한 Runtime의 지원 버전·CPU 목록. 버전 문자열만으로 호환성을 추정하지 않는다. | Host·Runtime 담당; [#23](https://github.com/casing1/praxioj/issues/23) |
| KVM 또는 선택한 gVisor Platform | 제안한 Firecracker/KVM 경로는 실제 Device, 서비스 신원 권한, API와 가상화·중첩 사전 조건을 검증한다. gVisor는 지원되는 Interception Platform을 명시적으로 선택해 조건을 검증한다. 실패를 기록하고 광범위한 접근을 자동 부여하지 않는다. | Host·Runtime 담당; [#23](https://github.com/casing1/praxioj/issues/23) |
| Namespace·Process 경계 | 적용하는 Mount·PID·IPC·User·Network 분리의 실제 상태를 확인하고 Host PID Namespace·Runtime Socket 노출을 금지한다. 동시 Job 2개와 후속 Job의 깨끗한 상태를 시험한다. | Launcher·보안 담당; [#23](https://github.com/casing1/praxioj/issues/23), [#27](https://github.com/casing1/praxioj/issues/27) |
| cgroup·시스템 자원 | 가용·위임 Controller와 상위 유효 제한을 조사한다. Runtime·Collector Overhead와 Host 여유 용량을 포함해 합성 부하에서 CPU·Memory·PID 제한을 입증한다. v2 Mount 보고만으로 충분하지 않다. | 자원 담당; [#24](https://github.com/casing1/praxioj/issues/24) |
| 파일시스템·Artifact | Digest 고정 Read-only Root·Input, 새 제한 Scratch·Output, 저장소·Home·DB·Backup·Socket Mount 배제. 신뢰할 수 없는 출력을 수집할 때 경로·Link·Special File 거부와 실제 Byte·Inode 제한을 검증한다. | Runtime·Collector 담당; [#23](https://github.com/casing1/praxioj/issues/23), [#24](https://github.com/casing1/praxioj/issues/24) |
| 네트워크 | Guest Egress·다른 Job·Host·Control Plane 접근을 기본 차단한다. 통제된 합성 대상으로 IPv4/IPv6 TCP/UDP/DNS, Host Gateway·Metadata 경로를 독립 검증한다. Proxy 상속·Platform Network 공유를 금지한다. | 네트워크·보안 담당; [#25](https://github.com/casing1/praxioj/issues/25) |
| Runtime·Image 출처 | Runtime·Launcher·Host/Guest Kernel·Root Filesystem의 Digest·버전을 고정하고 신뢰된 Build·Source·갱신·라이선스 정책을 기록한다. Mock Image Digest는 합성 식별자만 증명한다. | Runtime·Release 담당; [#23](https://github.com/casing1/praxioj/issues/23) |
| 최소 권한·비밀정보 | 전용 서비스 신원, 문서화된 최소 Launcher 권한과 권한 하향, 허용 목록 환경변수, Platform DB·LLM·Session·Cloud 자격증명과 Host Socket 배제. 합성 Canary로 확인한다. | Launcher·보안 담당; [#23](https://github.com/casing1/praxioj/issues/23), [#27](https://github.com/casing1/praxioj/issues/27) |
| 할당량·수용 제어 | Attempt별·전체 Overhead를 측정하고 Guest 외부에서 CPU·Memory·PID·Storage·Output·Time을 강제한다. 권위 있는 수명주기·Cleanup 증거로만 Host 예약 용량을 회수한다. 논리 Broker 예약은 OS Quota·청구 측정값이 아니다. | Broker·Runtime 담당; [#24](https://github.com/casing1/praxioj/issues/24) |
| Deadline·Cleanup Supervisor | 독립 Watchdog·Reaper, 전체 Process Tree·VM 종료, Orphan 정리, 제한된 수집과 Cleanup 불확실 시 Host 격리. 취소·Worker 종료·Broker 장애·Host 재시작을 검증하고 오래된 결과 권한을 별도로 폐기한다. DB 보존 정리는 Host 자원 Cleanup이 아니다. | Supervisor·운영 담당; [#26](https://github.com/casing1/praxioj/issues/26) |
| 독립 수용 검증 | 실제 Host·Runtime 설정을 검토하고 기록한 리비전에서 정상·거부·동시성·장애 시험을 실행한다. 미지원·미검증 제어를 명시한다. | 독립 검토자; [#27](https://github.com/casing1/praxioj/issues/27) |

cgroup v2의 Controller 가용성과 하위 트리 활성화는 다르며 Kernel 문서는 계층·위임 제약도 정의한다. 향후 조사는 Docker 메타데이터로 추정하지 않고 실제 서비스 하위 트리를 확인해야 한다. [Linux cgroup v2 문서](https://docs.kernel.org/admin-guide/cgroup-v2.html).

## 신뢰 경계와 호환성

Control Plane은 DB·계정·Provider와 권위 있는 Lease·Fence 상태를 유지한다. 향후 실행 호스트에는 고정 Attempt Input과 Supervisor가 필요한 제한 동작만 전달한다. Guest에는 재사용 가능한 Broker Capability나 Control Plane 자격증명을 전달하지 않는다. Runtime Launcher·파일 수집·OS 정책·권한 있는 설정은 독립 Framework 외부 및 API·AI Worker의 참가자 실행 경로 외부에 둔다.

M6-A 합성 채널은 프로토콜 증거다. 향후 공개 배포의 인증이나 OS 보안 경계를 입증하지 않는다. 실제 Transport 신원 발급·TLS·Peer 인증과 Linux 격리는 별도 수용이 필요하다. 알 수 없는 Runtime·Platform, 출처 검증 실패, 자원 부족·미지원 정책은 네이티브 실행·일반 Container·다른 Runtime으로 대체하지 않고 안전하게 거부한다.

이 사전 점검 문서는 API·DB Schema·Runtime 선택을 바꾸지 않는다. 기존 기본 Unavailable와 Mock 출처를 유지한다. 보안 맥락은 기존 [위협 모델](../../../architecture/sandbox-threat-model.md)과 [격리 설계](../../../architecture/sandbox-architecture.md)를 따른다.

## 검증·최적화·남은 작업

여기서 검증한 범위는 읽기 전용 개발 호스트 조사, 공식 문서 검토와 M6-B 요구사항·Issue 연결이다. 전용 Host의 KVM·API 접근, 선택한 Runtime 시작, Namespace·cgroup 강제, 파일시스템·네트워크 격리, 비밀정보 분리, OS 자원 제한, 작업 호환성, Guest 종료·정리, Host 복구와 성능은 미검증이다.

Reviewed; no justified optimization이다. Runtime I/O·Heartbeat·DB 경로나 Launcher를 추가하지 않았다. 후보 성능·Overhead는 실제 선택한 Linux 호스트에서 비교 가능한 조건으로 측정해야 한다. Vendor 설명이나 Docker VM의 보고 자원으로 속도·격리 순위를 추론하지 않는다.

Issue #20은 M6-B 완료를 가정하지 않고 조사 결과·요구사항·한계로 수용할 수 있다. 최종 구현 PR의 전달 기록에 정확한 리비전·CI 링크를 남긴다. 실제 Host 생성·설정·수용 시험은 Open M6-B의 [#23](https://github.com/casing1/praxioj/issues/23)–[#27](https://github.com/casing1/praxioj/issues/27)에 남는다. 공개 배포와 무제한 Code·Terminal·Network 접근은 범위 밖이다.

## 참고

2026-11-15 (Asia/Seoul) 공식 자료를 확인했다. Live Vendor 문서는 바뀔 수 있으므로 M6-B 승인 시 정확한 Runtime Release 요구사항을 선택·보존한다.

- [Firecracker 시작 안내](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md)
- [Firecracker 운영 호스트 설정](https://github.com/firecracker-microvm/firecracker/blob/main/docs/prod-host-setup.md)
- [gVisor 설치](https://gvisor.dev/docs/user_guide/install/)
- [gVisor Platforms](https://gvisor.dev/docs/architecture_guide/platforms/)
- [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)
- [M6-A 사전 점검 Issue #20](https://github.com/casing1/praxioj/issues/20), [M6-B Milestone](https://github.com/casing1/praxioj/milestone/2)
