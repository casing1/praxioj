# Linux host and isolated runtime preflight — Issue #23

[한국어](../i18n/ko/development/linux-runner-preflight.md) · [Documentation index](../README.md)

## Purpose, scope and decision

This is the read-only M6-B investigation for [Issue #23](https://github.com/casing1/praxioj/issues/23), extending the historical M6-A preflight. The maintainer confirmed that **no dedicated Linux execution host is available** for this task. Local investigation, release-specific comparison, integration design and documentation can proceed; actual supported-host acceptance cannot.

**Operational runtime selection: Blocked. Firecracker: Provisional. gVisor: Provisional. Execution approval: not granted.** Neither candidate is selected, installed or executed. Native macOS execution is not a supported Linux deployment path. A provisional candidate is a subject for later evaluation, not authority to enable a backend. Issue #23 and [M6-B](https://github.com/casing1/praxioj/milestone/2) remain Open until actual host evidence and their exit conditions are satisfied.

This change adds no launcher, dependency, transport listener, host policy or executable backend. Judge remains unavailable by default; Mock provenance and Framework/Platform separation remain intact. No VM/container was created or started for host probing, no VM was entered, no remote host contacted, and no `sudo`, runtime installation, system/firewall/virtualization change or untrusted execution occurred. Existing local services stayed stopped and the PostgreSQL volume was preserved. Standard repository regression/CI tests are separate from host/runtime acceptance.

## Evidence classes

| Status | Meaning |
| --- | --- |
| Observed | The named read-only query returned the stated fact, limited to that surface and timestamp; not an isolation pass |
| Not satisfied | A known current environment fails a required prerequisite, such as native Darwin versus required Linux |
| Unknown | The available observations do not establish the property, including Docker VM KVM/nesting/LSM state |
| Not Tested | No relevant functional, enforcement, workload or failure test was performed |
| Blocked | Required target access or evidence is absent; no selection/activation or Issue closure follows |

An item may have observed metadata and still have an Unknown or Not Tested effective control. Do not replace either with Pass. A4–A12 in the [isolation proposal](../architecture/sandbox-architecture.md#threat-to-control-and-acceptance-mapping) are not passed by this investigation. Existing M6-A protocol/backup tests retain their own scope; they are not new OS acceptance results.

## Current observations

Observation time: **2026-11-15 17:16:11 Asia/Seoul** (`2026-11-15T08:16:11Z`). The host inventory contains aggregate public-safe facts, not usernames, serial numbers, credentials, raw Docker environments or private endpoint paths.

| Surface | Actual observation | Boundary |
| --- | --- | --- |
| Native OS/CPU | macOS `27.0.1`, build `26A434`; Darwin `27.0.0`, `arm64`, Apple M2; 8 logical/physical CPUs | Native host is not Linux; architecture alone does not establish runtime/workload compatibility |
| Virtualization metadata | `kern.hv_support=1`; Hypervisor.framework present; `hw.optional.arm64=1` | Advertised native support is not a usable Linux KVM API, Docker VM nesting or permission test |
| Native KVM/runtime search | `/dev/kvm` absent; `firecracker`, `jailer`, `runsc` absent from searched native PATH | No device open/ioctl, binary execution or complete filesystem search; Docker VM state remains Unknown |
| Operator identity | Current native process is not root | Not a dedicated Linux runner account or a privilege-dropping proof; Docker control authority remains separate |
| Native resources | Physical RAM `17179869184` bytes; disk total `494384795648`, available `135564394496` bytes; filesystem reports `1323871040` available inodes | Instant shared native filesystem/memory observations, not reserved Linux guest capacity or enforced quotas |
| Native memory snapshot | `vm_stat` reports 4,278 free pages, 16,384 bytes/page | Free pages alone exclude reclaimable/compressed/inactive effects; no reliable runner admission budget is inferred |
| Docker context | Selected existing `desktop-linux`; two inventoried contexts use local Unix endpoints; no `DOCKER_HOST` override | No remote execution host identified or contacted; endpoint paths omitted |
| Docker versions | Client/server `29.4.3` | Version output does not certify isolation |
| Engine VM metadata | Docker Desktop; LinuxKit `6.12.76-linuxkit`, `aarch64`; 8 CPUs, `8321994752` bytes reported memory | Engine-reported VM totals; actual free VM disk/memory and dedicated-host suitability not measured |
| Engine facilities | cgroup v2, `cgroupfs`, `overlayfs`; security options report built-in seccomp and `cgroupns` | No controller delegation/effective limits, namespace behavior, seccomp denials or active LSM profile tested |
| Engine runtime inventory | Reports `runc` and `io.containerd.runc.v2`, default `runc` | No approved Firecracker/gVisor runtime shown; not a search of every VM file or a sandbox approval |

Reproducible read-only query families: `uname -srm`, `sw_vers`, `sysctl -n` for the listed hardware flags/counts, `vm_stat`, `statvfs`/disk usage, native PATH lookup, and selected local Docker context/version/info field projections. Docker output was filtered before recording; do not publish expanded `compose config`, raw `docker inspect`/environment, private connection details or credentials. Queries performed no installation, KVM open/ioctl, namespace creation or enforcement test. No permanent collection tool is added: these bounded operator observations do not justify a new runtime dependency or generic remote probe.

## Linux Host Acceptance Matrix

| Evaluation item | Current evidence/status | Evidence required on an approved dedicated Linux target |
| --- | --- | --- |
| Target identity/ownership | Blocked: maintainer reports no dedicated host | Approved target and operator, observation time, intended service identity and allowed non-destructive inspection scope |
| OS/kernel/architecture | Native Darwin: Not satisfied; Docker Linux metadata: Observed only | Exact distribution/kernel/config/page size and CPU architecture matched to the selected release/platform matrix |
| CPU virtualization | Native advertised flag: Observed; Linux facilities: Unknown | Actual relevant CPU/kernel interface under the intended identity; processor model or marketing support alone is insufficient |
| KVM device/access/API | Native path absent; target Unknown/Blocked | If required: device type/permissions and an authorized API-version query; no VM creation in #23. Device presence or access bits alone do not establish functionality |
| Nested virtualization | Unknown | Establish whether the target is virtualized and whether selected runtime requirements are available; justify Not Applicable only for a demonstrated applicable platform, not by assumption |
| cgroup v2 | Docker metadata Observed; effective control Unknown | Available/delegated CPU, memory, PID and relevant I/O controllers, actual subtree placement and ancestor limits; enforcement testing belongs to #24 |
| Namespace support | Docker `cgroupns` metadata only; other effective separation Unknown | Kernel support, service permissions and proposed mount/PID/IPC/user/network isolation; effective containment remains Not Tested |
| Seccomp/LSM | Engine built-in seccomp label Observed; effective filters/LSM Unknown | Selected runtime's syscall-filter requirements and active LSM/profile policy, including denied unsafe configurations |
| Dedicated account/privileges | Current native non-root operator only; target Blocked | Dedicated identity, exact launcher setup/drop model, device/controller permissions and reviewed authority with no blanket root/privileged fallback |
| Runtime installation/provenance | Native PATH/Engine inventory only; target Blocked | Architecture-specific runtime and companion artifacts, approved origin/version/digests, verification and update ownership |
| Kernel/image/root filesystem | No target artifacts; Blocked | Approved host/guest kernel and config, immutable rootfs/OCI digest, builder/source/license/SBOM and applicable signature/attestation policy |
| Disk/memory/headroom | Native snapshots and Engine totals only; target Blocked | Actual target free memory/storage/inodes, aggregate workload budgets, measured runtime/collector/reaper overhead, host reserve and admission plan |
| Effective filesystem/network/resources | Not Tested | #24/#25 synthetic positive/negative checks on the actual selected configuration; labels/flags are not proof |
| Cleanup/failure/recovery | Not Tested | #26 independent watchdog/reaper and allocation reconciliation, then #27 actual failure/containment acceptance |

## Versioned source basis and provenance limits

Official sources were inspected on 2026-11-15. Candidate references are **Firecracker v1.18.0**, source commit `eaf83bb718a559d324613d566eaf776b31a62340`, and **gVisor release-20261109.0**, commit `a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9`. These are source-documentation pins, not verified executable, guest-kernel, rootfs or installed-host digests. Release/checksum metadata was read; no runtime artifact was downloaded, installed, hashed, executed or signature/attestation verified. Re-evaluate pins and advisories before later adoption. [FC release][fc-release], [gVisor release][gv-release].

The evaluated Firecracker deployment is the ordinary Linux/KVM path. Its pinned kernel policy lists 4 KiB host/guest kernel lines 5.10, 6.1 and 6.18. Docker's observed LinuxKit 6.12 is not on that list; this is neither acceptance nor an experiment proving incompatibility. v1.18.0 also introduces a Nitro alternative; it needs different infrastructure and separate review and is not an automatic no-KVM fallback here. [Requirements][fc-start], [kernel policy][fc-kernel], [release][fc-release].

The pinned gVisor installation guide lists Linux 5.6+ and x86_64/ARM64; its packaging includes `gvisor-bin/` companions alongside `runsc`. An actual target needs the complete architecture-specific artifact set and selected platform's requirements, not just a copied binary or a generic rootless label. [Installation][gv-install], [platforms][gv-platform].

## Runtime Candidate Comparison

Vendor-described properties below are requirements/design inputs, not observed PraxiOJ isolation or performance.

| Evaluation Item | Firecracker v1.18.0 | gVisor release-20261109.0 |
| --- | --- | --- |
| Host Requirements | Evaluated ordinary path: Linux and functional KVM under the service identity; supported kernel/config/page-size matrix | Linux 5.6+; compatible selected `systrap` platform; KVM platform additionally needs usable KVM |
| Architecture Compatibility | x86_64/aarch64; exact runtime, host/guest kernel and workload combination pending | x86_64/ARM64; exact platform, runtime artifact set and workload combination pending |
| Isolation Boundary | Separate guest Linux per microVM with VMM/KVM and host controls | Sentry userspace Linux-ABI boundary; KVM platform retains a process model, not a full guest Linux VM |
| Required Privileges | Privileged jailer setup followed by dedicated UID/GID; exact minimal setup permissions need review | Depends on OCI, user namespace, mount, network and cgroup path; rootless alone is insufficient evidence |
| Filesystem Isolation | Approved kernel/rootfs/block backing plus constrained jailer tree; host exposure must be explicitly bounded | OCI rootfs/mount authority, Gofer and selected directfs behavior; reject unsafe host mounts |
| Network Isolation | TAP/namespace and external host filtering; VMM alone does not supply traffic filtering | Netstack configuration; `--network=none` still leaves internal loopback; host networking is outside the proposed policy |
| Resource Enforcement | VM sizing plus effective host cgroups/rlimits and independent deadline/output controls | Effective host cgroups including Sentry/workload memory; host PID counts differ from internal task counts |
| Operational Complexity | Kernel/rootfs, jail, network, cgroup, VMM and orphan lifecycle | OCI bundle, runtime companions, Sentry/Gofer, mount/cgroup and orphan lifecycle; no measured cost ranking |
| Verified Environment | No runtime or guest executed; native/Docker metadata only | No `runsc` or workload executed; native/Docker metadata only |
| Unverified Requirements | Dedicated host/KVM, privileges, provenance, policy enforcement, workload compatibility and failure/cleanup | Dedicated host/platform, seccomp/OCI/delegation, syscall/workload compatibility, provenance and failure/cleanup |

Sources: [FC design][fc-design], [jailer][fc-jailer], [host setup][fc-host]; [gVisor platforms][gv-platform], [filesystem][gv-fs], [networking][gv-net], [resources][gv-resources], [rootless][gv-rootless]. Neither boundary eliminates orchestration, kernel, collector or configuration risk.

### Candidate-specific checks before any selection

- Firecracker: verify actual jailer/VMM identity, syscall policy and effective cgroup membership; a requested cgroup path is not proof of placement. Caller-owned orphan/reaping logic must handle the real VMM, not assume a jailer PID or cooperative shutdown kills it. The exact reviewed launcher privilege model remains unresolved. [Jailer][fc-jailer], [production host setup][fc-host].
- gVisor: choose an exact launch path. The pinned built-in `--rootless` path has lifecycle/network limitations and can ignore cgroup configuration errors; the native OCI rootless path has different namespace limits. Do not recommend either without proving the required network/controller behavior. Its production guide is not a complete guide for this untrusted-code use case. [Rootless][gv-rootless], [production scope][gv-prod].
- gVisor: select filesystem/directfs and network modes explicitly; do not use host networking or trusted mounted resources as a compatibility workaround. Compiler/JIT, fork/threads, signals, mmap, dynamic loading/native extensions and file I/O need the exact planned Judge language/toolchain workload tests. Upstream application examples do not establish PraxiOJ compatibility. [Filesystem][gv-fs], [networking][gv-net], [compatibility][gv-compat].
- Both: cleanup latency, startup time, memory overhead, supported workload coverage, actual isolation and host availability are **Not Tested**. No security-strength, cost or speed ranking is measured.

### Selection rule

1. Retain Blocked until a dedicated approved Linux target and provenance evidence exist.
2. If its actual KVM/architecture/kernel/identity prerequisites match the pinned Firecracker path, evaluate that candidate first with separately authorized safe work. Do not select it from a version string, CPU name or device listing.
3. If that path cannot satisfy prerequisites, assess a supported gVisor platform, including `systrap` where appropriate. Missing KVM does not automatically establish gVisor suitability.
4. Select only after the supported-host evidence is reviewed. Selection still does not authorize untrusted execution: #24–#27 and A4–A12 acceptance remain separate gates. No fallback to native macOS, ordinary containers or another runtime is permitted.

## Required host configuration and provenance

These are future requirements, not changes applied in #23:

| Requirement | Required concrete record / enforcing owner |
| --- | --- |
| Dedicated host and identity | Approved disposable execution target, dedicated service account, no shared API/AI-worker identity; operator documents exact setup/drop authority and patch responsibility |
| Credential separation | No PostgreSQL, LLM, account/session/CSRF, cloud or agent credentials in guest environment/files/proc/output; supervisor receives only narrow control-channel authority; prove with synthetic canaries in #25/#27 |
| Minimal launcher privileges | Fixed approved runtime/image identifiers and constrained policy values; no caller host paths/flags/shell; enumerate required device/mount/controller/namespace operations and verify dropped privilege before work |
| Provenance manifest | For runtime/jailer or runtime companions, host and applicable guest kernel/config, rootfs/OCI image and approved toolchain: version, architecture, origin/build recipe, immutable artifact digest, verification policy/result, license/SBOM, owner and update/revocation procedure |
| Filesystem/network | Read-only approved root/input, fresh bounded scratch/output, no host home/repository/DB/backup/runtime-socket mounts; default-deny guest external/host/peer traffic and no inherited proxy; verify actual IPv4/IPv6/DNS/TCP/UDP behavior |
| Resource sizing | Define per-attempt CPU, elapsed time, memory/swap, PID, storage/inode, output and collector budgets. Reserve measured VMM/Sentry/Gofer/launcher/collector/watchdog overhead plus host headroom; verify controller ancestry and aggregate caps before increasing concurrency |
| Cleanup | Independent watchdog/reaper and durable allocation identity/generation; uncertain cleanup quarantines capacity; bounded output collection and host-restart reconciliation before reuse |

There is **no measured numeric hardware procurement minimum**. Derive target capacity from admitted job budgets plus measured runtime/support overhead and host reserve; current Mac/Docker totals do not establish that capacity. A dedicated supported Linux host can be bare metal or a suitable VM only after its required virtualization/nesting, permissions and runtime compatibility are established. No target is provisioned or purchased in this task.

## M6-A integration assessment

| Integration area | Reusable current control | Additional reviewed interface / unresolved prerequisite |
| --- | --- | --- |
| Separate-host identity | Constructor-observed Mock identity, pinned worker/attempt | Enrolled/revocable service identity supplied by authenticated peer verification and approved host/runtime registry, never by payload name |
| Authenticated channel | Bounded in-memory versioned wire messages; no Runner listener | Established encrypted peer-authenticated transport, bounded I/O/negotiation/timeouts, provisioning/revocation and reconnect/receipt semantics |
| Per-job authority | Private Broker lease; three narrow hashed operation grants, rotation and fence/digest checks | Bind approved host/allocation generation; explicit artifact/status permissions; keep original Broker lease and channel grants outside the guest |
| State/heartbeat | DB-authoritative renewal/expiry, joined local loop | Distinguish authenticated observations from authoritative state; remote lost-ack recovery without accepting replay; host-local independent deadline |
| Expiry/cancellation | Terminal fence/revocation and stale-result denial; persisted owner cancellation confirmation | A cancelled/expired DB job does not stop a real guest: independently signal, kill, reap and reconcile under partition/failure |
| Artifacts/results | Strict M5 correlation, inline UTF-8 size/hash/path/criterion and 64 KiB envelope checks | Bounded trusted collector for actual regular files, descriptor/type/link/race checks; explicitly version any binary/larger channel, no arbitrary URLs or host paths |
| Secrets | Backend receives request only; gateway retains Broker/settings/DB authority | Separate execution service/guest identity, no Platform network/mount/credential inheritance; canary evidence before connecting a real workload |
| Host loss/cleanup | Transient channel closure and persisted lease recovery; database history retention | Durable physical allocation/cleanup state, independent reaper/orphan reconciliation and quarantine; release physical capacity only after verified teardown |

Current terminalization releases a **logical output reservation**; it cannot authorize real host-capacity reuse. Current stop-and-wait heartbeat grant rotation and one-result channel closure also need explicit remote lost-ack/lost-receipt handling before another transport is designed. None of those interfaces is added here. Source paths: `apps/api/src/praxioj_api/judge.py`, `judge_runner.py`, `judge_routes.py`; Framework `execution/runner.py`, `execution/protocol.py`, `evaluation/execution.py`.

Preserve `in_memory_mock`, `synthetic_only=true`, `host_isolation_verified=false`, `provenance=synthetic_mock` and `independent_execution_evidence=false`. Current validators require `not_required/synthetic_no_resources` cleanup and no measured resource usage. Future enum names in the request/cleanup models do not implement execution. There is no current `execution_status` field: `ExecutionResult.status` and `JudgeJob.state` have their existing distinct meanings. Real execution needs separately reviewed/versioned contracts and validation, not widening or relabeling Mock claims. [Runner contract](../specifications/runner-protocol.md), [lifecycle](../architecture/judge-lifecycle.md).

## Unresolved dependencies and M6-B sequence

| Stage | Prerequisite and deliverable | Current status |
| --- | --- | --- |
| #23 host/runtime preflight | Approved real target/service-identity inventory, matched candidate requirements and artifact provenance; maintain reviewed host manifest | Blocked for actual host acceptance; local research/design/docs can merge with `Refs #23` |
| #24 resource/filesystem controls | After selected-host evidence, implement the fixed approved launcher policy, host reservations/limits and bounded collector using separately approved synthetic workloads | Not implemented / Not Tested |
| #25 network/secret separation | Establish actual deny policy, no inherited Platform authority and synthetic canary/probe plan before service/workload connection | Not implemented / Not Tested |
| #26 watchdog/cleanup/integration | Independent kill/reap/orphan/host-restart reconciliation and physical-capacity quarantine; explicitly assign authenticated transport and receipt work before activation | Not implemented / Not Tested |
| #27 independent acceptance | Actual supported-host configuration and positive/negative/failure/adversarial evidence across A4–A12, reviewed findings and residual limits | Not implemented / Not Tested |

Design preparation for #24/#25 may proceed after selection, but no participant-facing or untrusted-code service activation may precede required cleanup and independent acceptance. Earlier controlled synthetic validation workloads require separate explicit approval and applicable safety controls; this #23 task authorizes none. This sequence does not create new duplicate Issues or silently broaden their implementation scope; confirm specific interface ownership in the existing Issues before later work. Host access, policy application, installation, provisioning and execution require separate authorization.

## Verification, optimization and references

[Issue #23 validation](validation-issue23.md) records actual observations, static contract checks, regressions, CI/CodeQL and delivery. Mock/SQLite/CI success does not certify the absent Linux target or change Issue #23/M6-B acceptance. The [M6-A report](validation-m6a.md) remains historical implementation evidence; [SECURITY](../../SECURITY.md) and the [isolation proposal](../architecture/sandbox-architecture.md) retain the current boundaries.

**Reviewed; no justified optimization.** This work adds no runtime code, probe service, dependencies or duplicated execution contract. Reuse existing Broker controls and add future interfaces only when their real-host requirements are established. No startup/cleanup/overhead or security-performance improvement is measured. The separate post-documentation hardening review verifies least privilege, evidence classifications, unchanged defaults and accurate blocked gates; its actual result belongs in the validation record.

### Pinned official sources

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

References are pinned for reproducibility, not proof of installed artifact authenticity. Verify the selected release's complete artifacts, security notices, source/build and update policy on the actual target before adoption. The general [Linux cgroup v2 specification](https://docs.kernel.org/admin-guide/cgroup-v2.html) explains hierarchy/delegation; reading it does not establish any local enforcement.
