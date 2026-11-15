# Linux Runner compatibility and isolation preflight

[한국어](../i18n/ko/development/linux-runner-preflight.md) · [Documentation index](../README.md)

## Overview and status

This document records the M6-A investigation in [Issue #20](https://github.com/casing1/praxioj/issues/20): current development-host observations, official runtime prerequisites and the evidence required on a future dedicated Linux execution host. It is a non-executing preflight, not approval of an isolated Runner. No dedicated Linux host was accessed, no runtime was installed, and no operating-system, firewall or virtualization setting was changed.

PraxiOJ remains a localhost development preview with real untrusted execution unavailable. M6-A lifecycle and synthetic communication tests cannot pass the operating-system acceptance gates in [the isolation proposal](../architecture/sandbox-architecture.md). Actual isolated execution belongs to [M6-B](https://github.com/casing1/praxioj/milestone/2), which remains open.

## Scope and non-goals

The investigation covers kernel/architecture, KVM, candidate runtimes, namespaces/cgroups, filesystem/network boundaries, provenance, privilege, quotas and independent cleanup. It preserves the standalone Framework/Platform boundary and existing contracts. It does not provision a VM, select a production runtime, install Firecracker/gVisor, launch a guest or container workload, run participant/evaluator code, configure Linux facilities, or authorize a public Runner endpoint.

## Observed development environment

Read-only inventory was obtained on **2026-11-15 (Asia/Seoul)**. These are observations of this development setup, not supported-host certifications.

| Surface | Actual observation | What this does not establish |
| --- | --- | --- |
| Native host | `uname`: Darwin `27.0.0`, `arm64`; `sw_vers`: macOS `27.0.1`, build `26A434`; `hw.optional.arm64=1` | No native Linux kernel, namespace/cgroup enforcement or usable KVM interface was validated. |
| Docker client/server | Both report `29.4.3` | A Docker version is not an isolation acceptance result. |
| Docker Engine environment | `Docker Desktop`, kernel `6.12.76-linuxkit`, `aarch64`, 8 CPUs, `8321994752` bytes total memory | These are Engine-reported VM resources, not per-job allocations or available capacity guarantees. |
| Engine control metadata | cgroup v2 with `cgroupfs`; security options report built-in seccomp and cgroup namespace support | Metadata does not show the effective configuration of a future Runner or prove resource/escape/egress enforcement. |
| Native KVM path | `/dev/kvm` absent on the macOS host | KVM availability, nested virtualization, device access, ioctl behavior and permissions inside the Docker VM are **unknown**. Absence on macOS is not a finding about the VM. |
| Native executable search | `firecracker`, `jailer` and `runsc` absent from the native command search path | This only describes the searched host PATH; it is not a scan of the VM or every file on the host. |

The Docker VM was not entered for runtime/KVM probing. There is no evidence of a working Firecracker or gVisor installation, nor evidence authorizing an ordinary Docker container as a security sandbox. The observed macOS host cannot satisfy the proposed dedicated Linux/KVM deployment contract by silently substituting a host subprocess or container.

## Candidate runtime prerequisites

The proposed Firecracker path is specifically a **dedicated Linux/KVM host**. Official getting-started documentation describes x86_64/aarch64 Linux and read/write access to `/dev/kvm` for that path. Pin the selected release's supported kernel matrix and verify the actual device/API under the intended service identity before adoption. Other vendor deployment modes are not included in this proposal. [Firecracker prerequisites](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md).

Firecracker's production guidance calls for patched host/guest components, restrictive seccomp and jailer-equivalent constraints; guest-controlled output also needs host-side bounds. A quickstart boot is insufficient acceptance evidence. [Firecracker production host guidance](https://github.com/firecracker-microvm/firecracker/blob/main/docs/prod-host-setup.md).

gVisor's installation documentation currently lists Linux 5.6+ and x86_64/ARM64. Its platform guide distinguishes KVM from `systrap`; do not infer that every gVisor configuration needs KVM or that a supported architecture establishes application compatibility. A selected platform/version still needs its own workload, privilege and isolation tests. [gVisor installation](https://gvisor.dev/docs/user_guide/install/), [platform guide](https://gvisor.dev/docs/architecture_guide/platforms/).

These vendor prerequisites are necessary inputs, not PraxiOJ security guarantees or measured performance comparisons. Firecracker-first evaluation where a supported KVM host is available, with gVisor as a separately validated alternative, remains a proposal. No candidate is installed or approved here.

## Required Linux acceptance evidence

The following are **PraxiOJ requirements for M6-B**, not observed controls. Missing or unsupported requirements must leave real execution unavailable.

| Area | Evidence to collect on the dedicated host | Owner / tracking |
| --- | --- | --- |
| Kernel and CPU | Distribution/kernel build, architecture, patch policy and selected runtime's supported version/CPU matrix; verify compatibility without inferring it from a version string alone. | Host/runtime owner; [#23](https://github.com/casing1/praxioj/issues/23) |
| KVM or selected gVisor platform | For the proposed Firecracker/KVM path: actual device availability, service-identity permissions, API support and documented virtualization/nesting prerequisites. For gVisor: explicitly select a supported interception platform and verify its requirements. Record failures; never grant broad access automatically. | Host/runtime owner; [#23](https://github.com/casing1/praxioj/issues/23) |
| Namespaces and process boundary | Verify effective mount, PID, IPC, user and network separation where used; no host PID namespace or runtime socket exposure. Exercise two concurrent jobs and a clean subsequent job. | Launcher/security owner; [#23](https://github.com/casing1/praxioj/issues/23), [#27](https://github.com/casing1/praxioj/issues/27) |
| cgroup and aggregate resources | Inventory available and delegated controllers and effective ancestor limits; demonstrate CPU, memory and PID bounds under synthetic pressure, including runtime/collector overhead and host reserve. A reported v2 mount alone is insufficient. | Resource owner; [#24](https://github.com/casing1/praxioj/issues/24) |
| Filesystem and artifacts | Digest-pinned read-only root/input, fresh bounded scratch/output, no repository/home/database/backup/socket mounts; verify path/link/special-file rejection and actual byte/inode limits in a hostile-output collector. | Runtime/collector owner; [#23](https://github.com/casing1/praxioj/issues/23), [#24](https://github.com/casing1/praxioj/issues/24) |
| Network | Default-deny guest egress and peer/host/control-plane access; independently verify IPv4/IPv6 TCP/UDP/DNS, host gateways and metadata paths using controlled synthetic targets. Do not inherit proxies or share the Platform network. | Network/security owner; [#25](https://github.com/casing1/praxioj/issues/25) |
| Runtime/image provenance | Pin runtime, launcher, host/guest kernel and root filesystem digests/versions; record trusted build/source, update and license policy. A Mock image digest proves only a synthetic identifier. | Runtime/release owner; [#23](https://github.com/casing1/praxioj/issues/23) |
| Minimum privilege and secrets | Dedicated service identity; documented minimal launcher authority and privilege dropping; allowlisted environment, no Platform DB/LLM/session/cloud credentials or host sockets. Verify with synthetic canaries. | Launcher/security owner; [#23](https://github.com/casing1/praxioj/issues/23), [#27](https://github.com/casing1/praxioj/issues/27) |
| Quotas and admission | Measure per-attempt and aggregate overhead; enforce CPU/memory/PID/storage/output/time limits outside the guest. Reconcile reserved host capacity only from authoritative lifecycle/cleanup evidence. Logical Broker reservations are not OS quotas or billing measurements. | Broker/runtime owner; [#24](https://github.com/casing1/praxioj/issues/24) |
| Deadline and cleanup supervisor | Independent watchdog/reaper, whole-process-tree or VM teardown, orphan reconciliation, bounded collection and host quarantine on uncertain cleanup. Cover cancellation, worker kill, Broker outage and host restart; revoke stale result authority independently. Database retention is not host-resource cleanup. | Supervisor/operations owner; [#26](https://github.com/casing1/praxioj/issues/26) |
| Independent acceptance | Review the actual host/runtime configuration and run positive, negative, concurrency and failure tests against the recorded revision. Keep unsupported or unverified controls explicit. | Independent reviewer; [#27](https://github.com/casing1/praxioj/issues/27) |

For cgroup v2, controller availability and subtree enablement are distinct; the kernel documentation also defines hierarchy and delegation constraints. Future inventory must inspect the actual service subtree rather than infer effective limits from Docker metadata. [Linux cgroup v2 documentation](https://docs.kernel.org/admin-guide/cgroup-v2.html).

## Trust boundaries and compatibility

The control plane retains database, account, provider and authoritative lease/fence state. A future execution host receives only the pinned attempt input and narrow operations needed by its supervisor. The guest receives no reusable Broker capability or control-plane credentials. Runtime-specific launchers, filesystem collection, OS policy and privileged setup belong outside the standalone Framework and outside API/AI-worker participant execution paths.

The M6-A synthetic channel is protocol evidence only. It neither authenticates a future public deployment nor establishes a secure OS boundary. Real transport identity provisioning, TLS/peer authentication and Linux confinement require separate acceptance. Unknown runtime/platform, failed provenance, unavailable resources or unsupported policy must fail closed, without fallback to native execution, ordinary containers or a different runtime.

This preflight documentation changes no API, database schema or runtime selection. Existing default unavailable behavior and Mock provenance remain compatible. The existing [threat model](../architecture/sandbox-threat-model.md) and [isolation proposal](../architecture/sandbox-architecture.md) remain the security context.

## Verification, optimization and open work

Verified here: read-only development-host inventory, official-document review and an explicit mapping of unresolved requirements to M6-B Issues. Not verified: dedicated-host KVM/API access, selected runtime startup, namespace/cgroup enforcement, filesystem/network confinement, secret isolation, OS resource limits, workload compatibility, guest teardown, host recovery or performance.

Reviewed; no justified optimization. This investigation adds no runtime I/O, heartbeat/database path or launcher to optimize. Candidate-runtime performance and overhead require comparable measurements on the actual selected Linux host; no speed or isolation ranking is inferred from vendor descriptions or the Docker VM's reported resources.

Issue #20 can accept the documented inventory, requirements and limitations without assuming M6-B complete. The final implementation PR's delivery record supplies its exact revision and CI links. Actual host provisioning, configuration and acceptance remain [#23](https://github.com/casing1/praxioj/issues/23)–[#27](https://github.com/casing1/praxioj/issues/27) under open M6-B. Public deployment and unrestricted code/terminal/network access remain outside scope.

## References

Official sources consulted 2026-11-15 (Asia/Seoul); links to live vendor documentation may change. Select and archive the exact runtime-release requirements during M6-B approval.

- [Firecracker getting started](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md)
- [Firecracker production host setup](https://github.com/firecracker-microvm/firecracker/blob/main/docs/prod-host-setup.md)
- [gVisor installation](https://gvisor.dev/docs/user_guide/install/)
- [gVisor platforms](https://gvisor.dev/docs/architecture_guide/platforms/)
- [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)
- [M6-A preflight Issue #20](https://github.com/casing1/praxioj/issues/20), [M6-B Milestone](https://github.com/casing1/praxioj/milestone/2)
