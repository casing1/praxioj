# Issue #23 — Linux host and runtime preflight validation

[한국어](../i18n/ko/development/validation-issue23.md) · [Documentation index](../README.md)

## Target, scope and status

This record covers [Issue #23 — Dedicated Linux host and runtime provenance](https://github.com/casing1/praxioj/issues/23) in [M6-B — Isolated Linux Runner Validation](https://github.com/casing1/praxioj/milestone/2). It records read-only environment observations, candidate research, static contract review and the limits of the resulting documentation. The [Linux preflight](linux-runner-preflight.md) contains the Host Acceptance Matrix, candidate comparison, minimum-privilege requirements, unresolved dependencies and proposed implementation sequence.

**Actual runtime selection: Blocked.** The maintainer confirmed that no dedicated Linux execution host is available for this task. Firecracker and gVisor are **Provisional candidates**, with no execution approval. This documentation can be delivered independently, but Issue #23 and M6-B must remain **Open** until actual required host evidence exists. M6-B isolation acceptance A4–A12 is not established by this work.

No product runtime, database schema, execution contract, default backend or dependency is changed. No Linux host was provisioned or contacted; no SSH secrets or complete process environment was inspected. This local preflight performed no `sudo`, runtime installation, candidate-runtime VM/container workload, firewall/virtualization change, public listener or untrusted code execution. Default Judge selection remains unavailable, and Mock output remains synthetic.

## Revision, environment and baseline

Preflight started on clean local/remote main `2927336e8c8a25be1a4a5f60002aab0b1e48a9ff`. The Issue-linked branch is `docs/23-linux-runtime-preflight`. The root preflight found no open PRs and zero open Dependabot, CodeQL and Secret Scanning alerts. Existing protected-main and squash-merge rules remain in force. Existing data, stopped local containers and the named PostgreSQL volume were preserved.

The initial documentation baseline was **66 Markdown files and 18 maintained translation pairs**. The local documentation checker, dependency consistency and license-notice checks passed before edits. This document does not present historical M6-A full-suite counts as new Issue #23 executions; the [M6-A report](validation-m6a.md) retains those results separately.

Observation timestamp: **2026-11-15T08:16:11Z / 2026-11-15 17:16:11 KST**. The source was a narrowly scoped local inventory of native macOS and selected Docker Desktop metadata. Temporary observation JSON stays outside the repository; no raw host inventory is committed. The safe aggregate facts below do not identify a remote host or disclose credentials.

## Observed facts and evidence limits

| Surface | Actual observation | Acceptance interpretation |
| --- | --- | --- |
| Native OS/kernel | Darwin `27.0.0`, macOS `27.0.1`, build `26A434` | Observed macOS; it does not satisfy the dedicated Linux host prerequisite. |
| Native CPU | `arm64`, Apple M2, 8 logical and 8 physical CPUs | Hardware identity only; selected Linux runtime and guest compatibility remain untested. |
| Native virtualization metadata | `kern.hv_support=1`; Hypervisor.framework present | Apple framework support is not Linux KVM/API access or nested-virtualization evidence. |
| Native KVM path | `/dev/kvm` absent; no device open/ioctl attempted | Only the native macOS path was checked. KVM, nesting and intended-service-account access inside the Docker VM are Unknown. |
| Native identity | Current operator is non-root | This is not a provisioned Runner account or proof of launcher least privilege. |
| Native memory | `17179869184` bytes physical RAM; `vm_stat` reports 4278 free pages of 16384 bytes | A time-specific host snapshot; free pages are not an available-memory or per-job admission guarantee. |
| Native filesystem | Total `494384795648` bytes; available `135564394496` bytes; available inodes `1323871040` | Volatile local filesystem observations, not dedicated-host storage allocation or enforceable job quotas. |
| Native executable search | `firecracker`, `jailer` and `runsc` absent from the searched PATH | Not a search of every file or the Docker VM; no installed runtime provenance was verified. |
| Docker versions/context | Client/server `29.4.3`; selected local Desktop context | Selected local Engine metadata only; no remote Docker host was contacted. |
| Docker VM metadata | Docker Desktop, kernel `6.12.76-linuxkit`, `aarch64`, 8 CPUs, `8321994752` bytes reported total memory | Engine-reported VM resources, not actual free/allocatable capacity or an approved execution host. |
| Docker control metadata | cgroup v2 / `cgroupfs`, `overlayfs`, built-in seccomp and cgroup namespace options; reported runtimes `runc` and `io.containerd.runc.v2` | Not effective Runner controller delegation, namespace isolation, LSM enforcement or hostile-workload acceptance. |

The Docker VM was not entered. No privileged container or diagnostic workload was started to discover capabilities. Actual controller delegation, namespace configuration, seccomp/LSM profiles, service-identity privileges, KVM usability, nested virtualization and runtime startup are **Unknown or Not Tested**, not passed. At observation, local containers were stopped and the existing database volume remained present; no local PostgreSQL instance was started for this documentation validation.

## Candidate research and provenance boundary

The candidate investigation records these upstream source references:

| Candidate | Inspected source pin | What remains unverified |
| --- | --- | --- |
| Firecracker | `v1.18.0`, commit [`eaf83bb718a559d324613d566eaf776b31a62340`](https://github.com/firecracker-microvm/firecracker/commit/eaf83bb718a559d324613d566eaf776b31a62340) | No installed binary, artifact digest/signature, host/guest kernel, root filesystem or compatible dedicated host was verified. |
| gVisor | `release-20261109.0`, commit [`a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9`](https://github.com/google/gvisor/commit/a0e6be6fb5e03d8ebea13592f36a097c7e9a41b9) | No `runsc` binary, artifact digest/signature, selected platform, workload compatibility or actual Linux host was verified. |

These are documentation/source pins, not deployed-runtime provenance or recommended production versions. No binary or guest image was downloaded, installed or executed. Vendor prerequisites and the Firecracker/gVisor platform distinction are detailed with official references in the [primary preflight](linux-runner-preflight.md). No security ranking, startup cost, memory overhead or host availability is inferred from those documents.

## Implementation and integration assessment

The change is documentation only. It preserves the Framework/Platform split and M6-A Broker, gateway, capability, lease/fencing, retention and result validation contracts. The review identifies future requirements instead of enabling a backend:

- Supply an authenticated, separately observed peer identity to a real transport; self-declared message identity and digest equality are not authentication.
- Keep API/PostgreSQL/LLM/session credentials outside the execution host's guest inputs. Keep runtime-specific launchers, privilege setup and collectors outside the independent Framework and API/AI-worker execution path.
- Retain current-attempt, operation, policy/input/image/request binding, expiry and replay checks; do not relax the fixed Mock protocol to admit unverified execution.
- Separate logical Broker reservation release from physical host-resource reuse. A terminal DB job, expired lease or synthetic cleanup acknowledgement does not establish that a real guest has stopped. An independent watchdog/reaper and authoritative cleanup confirmation must precede physical capacity reuse.
- Treat uncertain teardown, host restart and disconnected control channels as recovery/quarantine obligations, not reasons for transparent replay. Unknown runtime, provenance, isolation or capacity must keep execution unavailable.

Minimum host capacity must follow declared job budgets plus measured runtime/collector/watchdog overhead and a reviewed host reserve. This preflight invents no minimum CPU/RAM/disk purchase specification or performance figure. No permissions, cgroups, device access or host policy were changed to satisfy a paper requirement.

## Verification and actual results

| Check | Observed result and scope |
| --- | --- |
| Narrow native/Docker metadata inventory | Completed read-only at the timestamp above; no VM entry or runtime launch. |
| Local baseline documentation/dependencies/notices | Passed: 66 Markdown files / 18 translation pairs at baseline; dependency consistency and synchronized license notices. |
| Focused regression | **167 passed, 10 PostgreSQL-only skips, 1 existing Starlette warning; 29.80 s**. Exact command below; this is a focused local run, not the complete PostgreSQL/M6-B suite. |
| Static contract assertions | **9 assertions passed** against current identity/capability/provenance/result/request models; details below. No OS isolation exercised. |
| Governance checker regressions | **25 passed; 0.33 s**, `.venv/bin/python -m pytest -q tests/governance`; no skips. |
| Frontend tests / TypeScript / Vite | **33 passed; 3.27 s**. Build passed: JS 274.37 kB / gzip 82.90 kB; CSS 31.23 kB / gzip 7.45 kB; Vite reported 92 ms. No frontend behavior changed or performance improvement is claimed. |
| Post-change documentation links/translation pairs | Passed: 68 Markdown files; 19 registered translation pairs. Local destinations/fragments and reciprocal pairs checked offline; semantic review is separate. |
| Dedicated Linux/KVM/runtime/OS acceptance | **Blocked / Not Tested**: no approved Linux host, runtime startup or confinement tests. |
| Required remote CI/CodeQL/Governance | Pending PR creation and actual check receipts; not inferred from local passes. |

Focused regression command, with PostgreSQL test URLs explicitly absent:

```sh
env -u PRAXIOJ_TEST_DATABASE_URL -u TEST_DATABASE_URL .venv/bin/python -m pytest -q tests/framework/test_execution_protocol.py tests/framework/test_runner_protocol.py tests/api/test_judge_broker.py tests/api/test_judge_lifecycle.py tests/api/test_judge_runner.py
```

The 10 skips are 3 Broker PostgreSQL claim/result, cancel/result and admission races; 6 Lifecycle PostgreSQL clock/row-lock cases; and 1 Runner independent-channel result-commit race. No local PostgreSQL startup was used. The 9 introspection assertions checked `RunnerIdentity` transport `in_memory_mock`, `synthetic_only=True`, `host_isolation_verified=False`; `BackendCapabilities.untrusted_code_execution=False`; `ExecutionResult.provenance=synthetic_mock`; `SyntheticExecutionAssessment.independent_execution_evidence=False`; absence of `execution_status` and presence of `status` on the result model; and the `ExecutionInputSnapshot` request-input model. This is static contract evidence, not a deployed configuration or sandbox test.

Frontend receipts are `npm test` and `npm run build` for `apps/web`. Baseline dependency and notice receipts are `.venv/bin/python -m pip check` and `.venv/bin/python scripts/sync-licenses.py --check`; the Markdown/translation checker is `python3 scripts/check-docs.py`. Candidate source/version facts above come from the separately recorded reference investigation; the preparatory contract review and nine model assertions inspected repository source only. The later independent Firecracker source spot-check is recorded below.

No live or paid provider was used. PostgreSQL-only skips are reported instead of claiming SQLite verifies row locks or worker competition. Local unit/static results do not pass A4–A12. Formal code-security scanning is not claimed for this documentation change; the actual independent work is a read-only hardening/source-contract review.

## Dedicated optimization and hardening

An independent reviewer performed the separate post-documentation optimization/hardening pass against the canonical preflight, EN/KO validation and changed-path scope. Two precision findings were corrected: service activation gates now permit only separately approved controlled synthetic validation before final acceptance, and the static-check receipt lists exactly the nine assertions actually run. The reviewer verified both corrections and found no remaining blocking findings in that snapshot. The review preserved evidence classifications, minimum launcher authority, secret exclusion, unchanged synthetic contracts and physical-capacity quarantine. It did not perform host acceptance or a formal managed security scan; gVisor vendor-source facts rely on the primary reference investigation, since the independent spot-fetch encountered cache misses.

Conclusion: **reviewed; no justified optimization**. No runtime path, dependency, database round trip or launcher was added. Existing Broker contracts can be reused, while real transport and isolation controls need their own implementation and acceptance. No candidate-runtime performance was measured, so no efficiency or isolation-performance improvement is claimed. The pre-edit documentation/test baseline and post-edit offline checks establish regression scope, not a speed comparison.

## Issue #23 acceptance and unresolved dependencies

| Exit condition | Current status |
| --- | --- |
| Maintainer-approved dedicated Linux target and intended service identity | **Blocked**: maintainer confirmed no host available. |
| Actual kernel/CPU/platform prerequisites, KVM/API/nesting where required, resolved under intended identity | **Blocked / Unknown**; native and Engine metadata do not substitute for that evidence. |
| Verified installed runtime/launcher/kernel/rootfs provenance and update owner | **Not Tested**; source pins alone are insufficient. |
| Documented minimum privilege, credential separation, resource/cleanup owners and follow-up sequence | Documented requirements; not applied or verified host controls. |
| Local documentation/static regression evidence | Passed within the stated local scope; independent post-document review completed with two precision corrections. Not host acceptance. |
| Actual protected PR checks/review and metadata audit | Pending. |

**Issue #23 acceptance is not met.** A documentation-only PR may reference `Refs #23`, but must not use its merge to close the Issue or M6-B. No runtime is Selected or approved. After an explicitly approved supported host is available, resolve #23's actual provenance/prerequisites, then implement [#24 isolation/resources](https://github.com/casing1/praxioj/issues/24), [#25 network/secrets](https://github.com/casing1/praxioj/issues/25), [#26 teardown/recovery](https://github.com/casing1/praxioj/issues/26) and [#27 independent acceptance](https://github.com/casing1/praxioj/issues/27) according to their dependencies. Real execution remains unavailable until applicable OS gates and maintainer approval are actually satisfied.

## GitHub delivery and final state

The existing [Issue #23](https://github.com/casing1/praxioj/issues/23) and [Milestone 2](https://github.com/casing1/praxioj/milestone/2) are reused; no duplicate tracking object or speculative due date is created. The branch is Issue-linked. PR URL, actual assignee/labels/Milestone, required-check links, review findings, protected squash result and post-merge state must be read back and recorded at delivery. At this snapshot no PR check or merge is claimed.

README/CHANGELOG, primary preflight and index/translation registration are reviewed in the same delivery. Apache-2.0, contributor/third-party attribution, data preservation and localhost restrictions remain unchanged. This record's unresolved host prerequisite keeps Issue #23 and M6-B **Open**, regardless of whether the documentation PR itself is successfully merged.
