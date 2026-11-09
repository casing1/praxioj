# Runtime, tools, and resources

`praxioj.runtime` remains provider-neutral. `AIRuntime` accepts typed conversation history, `ModelConfig`, and `RuntimeContext`; it returns a `ProviderResponse` with nullable token usage and optional tool requests. The runtime does not execute a model's tool request. `MockProvider` and `OpenAICompatibleProvider` implement the same provider contract. The framework requires HTTPX, but no web server, database, or OpenAI SDK.

## Conversation and provider boundary

User, assistant, system, and tool roles remain distinct. HTTP participants can submit only user content. Tool result messages are created by the server and must reference an outstanding assistant tool-call ID. Call IDs must be unique among outstanding requests; a resolved ID can be reused by a later turn. The Platform separately rejects repeated IDs within one run. A response cannot insert a system message. Prompt injection in external text remains possible at the model level; authorization is enforced by application policy, regardless of model instructions.

The compatible adapter sends one bounded non-streaming Chat Completions request per call. It validates response structure, tool JSON and roles, enforces 1 MiB serialized request/response bounds and a total deadline, and supports asynchronous cancellation. HTTP errors, malformed responses, timeout, unsupported capabilities, and connection failures become safe typed errors. There is no automatic retry. Assistant response text is additionally capped at 20,000 characters, and request history at 500 messages. It requests uncompressed UTF-8 JSON and rejects compressed response bodies before decompression. Raw provider error bodies, headers, URLs, and credentials are not included in public errors or traces.

## Tools

Every `ToolSpec` includes ID, name, description, input/output JSON schemas, required permissions, and execution limits. Only trusted code registers handlers. A manifest supplies an allowlist, not import paths or code.

| Tool ID | Wire name | Input | Permission |
| --- | --- | --- | --- |
| `workspace.read_file` | `read_file` | `{path}` | `workspace:read` |
| `workspace.write_file` | `write_file` | `{path, content}` | `workspace:write` |

`ToolDispatcher.authorize` checks the known tool, problem allowlist, required permissions, strict schema, path, and per-file limit. Execution rechecks authorization and total workspace/count limits. Results record completion, denial, or failure; only a successful write emits an artifact modification. Read/write outputs include logical path, content, SHA-256, UTF-8 byte size, and revision. Tool messages allow up to 1 MiB of UTF-8 text so a legal 100,000-byte file and its JSON metadata fit; other message roles retain a 100,000-character limit. The complete serialized provider request still has its separate 1 MiB context bound.

Paths are relative logical keys, at most 128 characters. Each component starts with an ASCII letter, number, `_`, or `-`; subsequent characters may also include `.`. Components use single `/` separators. Absolute paths, dot components, backslashes, URL escapes, drive prefixes, and NUL are rejected. The Platform stores text rows keyed by session; it never joins a participant path to a host directory. `InMemoryWorkspaceStore` is the independent SDK reference implementation. The Platform binds each store to an authorized session, and tools cannot select a different session ID. This is application-level logical separation, not an OS sandbox or protection against a compromised API process. Host commands, network tools, arbitrary code, symlinks, and uploaded executables are absent.

## Resource accounting

Problem limits bound user messages, model attempts, tool requests, individual request duration, total run duration, file bytes, total workspace bytes, and file count. Calls are reserved before work, including unsuccessful attempts. Tool requests skipped because the run has ended or exhausted its allowance have denial traces but do not increase the admitted-tool-attempt counter. No database transaction spans a provider network wait. One run is active per session; updates use short transactions under the session lock. Deadlines stop further work but cannot preempt an already-running synchronous database or trusted built-in tool operation.

Compatible-provider `Usage.input_tokens` and `Usage.output_tokens` are independently nullable; absent counts remain `null`, including when only one count is reported. Platform token counters sum only known values. `usage_complete=false` means some values are unknown; displayed numbers are known subtotals, not invented exact totals. Mock estimates carry `estimated=true`. An optional `max_total_tokens` limit is based on observed usage: one in-flight response can exceed it, and unknown usage prevents further calls when that limit is enabled. This is not a guaranteed provider billing cap.

Cost estimates use only explicitly configured input/output prices per million tokens and the session's pricing snapshot. Missing prices/usage prevent a complete estimate. Estimates are not invoices; cached-token discounts, provider-specific rates, taxes, and billing reconciliation are not implemented.

## Platform execution

`POST /api/sessions/{id}/runs` accepts `{content, request_id}`. A retry with the same UUID and content returns the same run; different content with that UUID conflicts. Run states are `queued`, `running`, `completed`, `failed`, `cancelled`. Session states are `active`, `submitted`, `ended`. Only the owner can read or change sessions, runs, drafts, files, usage, traces, and evaluations.

The orchestrator stores assistant calls, authorization results, tool outputs, and modified files before continuing the conversation. Duplicate provider tool-call identities within a run are rejected before a repeated side effect; a new run may reuse an ID after the preceding call is resolved. Terminal runs release the active-run slot. Shutdown cancels tasks; startup marks interrupted work failed instead of repeating remote work. This is single-process scheduling, not a durable distributed queue or exactly-once remote execution.

The original synchronous `/messages` route remains for Mock sessions without tools and preserves its M1 response/event contract. It rejects active M2 runs and sessions requiring the asynchronous path. New UI uses `/runs`.

Final submission snapshots logical workspace artifacts and supplies the authorized trace to the existing evaluation engine. The built-in rubric still evaluates final text; M2 does not claim to grade collaboration quality merely because it records process evidence.
