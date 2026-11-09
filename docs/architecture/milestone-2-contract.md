# Milestone 2 implementation contract

M2 is an additive extension of the existing Apache-2.0 personal hobby project. No paid calls, new credentials, arbitrary code execution or host file access. Local development only. One API process owns in-process asynchronous runs; this is not a distributed worker.

## Ownership and compatibility

- Framework owner: runtime adapter, runtime models, tools, Problem SDK additions, tracing additions and focused tests. Backend owner: apps/api + tests/api. Frontend owner: apps/web. Root owns docs, examples, Compose/env, integration checks and final review.
- Keep all existing M1 behaviors and regression tests. Preserve the legacy synchronous POST /sessions/{id}/messages for mock/no-tools sessions with its original response and event contract; new workspace uses asynchronous /runs for M2 features. Do not call a network provider while holding a DB lock. Legacy endpoint must reject real-provider/tool sessions clearly and cannot bypass an active M2 run.
- Keep sample release-plan/1.0.0 unchanged. New M2 sample workspace-plan/1.0.0 schema1.1. SDK accepts1.0 and1.1; digest of1.0 manifests MUST remain identical to M1 (strip added fields when they equal compatibility defaults when hashing schema1.0; non-default policies still affect identity).
- New manifest fields: ai_policy {allowed_providers:[string] default [], allowed_models:[string] default [], max_output_tokens:1024, allow_temperature:true}, tool_permissions:[string] default []. Empty provider/model allowlist means operator-configured profiles allowed. Tool IDs workspace.read_file/workspace.write_file; permissions workspace:read/workspace:write; capabilities chat, tool_calling.
- ResourceLimits additions: max_model_calls=30, max_tool_calls=20, max_total_tokens:int|null=None, request_timeout_seconds=30 (1..120), max_run_seconds=90 (1..300), max_file_bytes=16384, max_workspace_bytes=65536, max_workspace_files=8. Hard call/time/file limits; optional total-token cap is an observed-usage limit, may overshoot by one in-flight call and fails closed on unknown usage. Never fabricate missing provider tokens.

## Runtime contract

Preserve imports from praxioj.runtime. Framework dependency httpx==0.28.1 (already in lock). No OpenAI SDK, framework remains provider-neutral.

- ProviderCapabilities(tools:bool=False, system_messages:bool=True, temperature:bool=True, token_limit_parameter:'max_tokens'|'max_completion_tokens'='max_tokens'); adapters expose capabilities.
- Message(role,content default '',tool_calls:list[ToolCall]=[],tool_call_id:str|null=None). ToolCall(id,name,arguments) stays. AI output may have empty content only with tool calls. Reject unsupported roles/invalid call correlations at provider boundary. Prior user/system boundaries stay explicit; only server creates tool messages.
- ModelConfig existing fields provider/model/temperature/max_output_tokens; model string must permit local model IDs with slashes. Never secrets/baseURL in ModelConfig. Temperature can be None for models that disallow it.
- Usage(input_tokens:int|null,output_tokens:int|null,estimated:bool=False) nullable usage; mock explicitly estimated=True. ProviderResponse adds provider_request_id:str|null, finish_reason:str|null, tool_calls, content (possibly empty with calls). No raw upstream headers/body retained.
- RuntimeContext adds tool_definitions:list[dict] (OpenAI function-tool wire schema); AIRuntime.respond supports final user OR tool message, validates caps, returns tool_calls without executing them. Loop orchestration in Platform; standalone caller can do same with tools interface.
- OpenAICompatibleProvider(base_url, api_key=None, capabilities=ProviderCapabilities(), timeout_seconds=30, transport=None). Uses httpx AsyncClient with trust_env=False, follow_redirects=False, bounded response/context size, POST base_url/chat/completions, safe typed ProviderError(code, retryable, http_status), ProviderTimeout. async cancellation propagates; no automatic retries; no provider secrets in errors/repr/logs. HTTP accepted only for loopback/local endpoint configuration; server explicitly controls URL; reject userinfo/query/fragment. No user chooses URL/key via API.
- MockProvider retains default predefined M1 behavior. For M2 tool-enabled context and marker prompt 'save a release plan', deterministically requests write_file(path='plan.txt',content='Goal: ... Verification: ... Risk: ...'), then after tool output responds completion. No command interpretation.

## Tools contract

`praxioj.tools` exposes ToolSpec, ToolRegistry, ToolDispatcher, ToolPolicyContext, AuthorizationDecision, WorkspaceDocument, WorkspaceStore, InMemoryWorkspaceStore, WorkspaceLimits, ToolExecutionOutcome, default_tool_registry.

- ToolSpec(id,name,description,input_schema,output_schema,required_permissions,execution_limits). Function names read_file/write_file; IDs workspace.read_file/workspace.write_file. Strict Pydantic concrete inputs/outputs. Unknown/excess fields, malformed JSON and traversal fail. Registry explicit trusted builtins; never imports names from packages.
- WorkspaceDocument(path,content,sha256,byte_size,revision). WorkspaceStore is already bound to a session; read(path)->WorkspaceDocument|None, write(path,content)->WorkspaceDocument, list_files()->list[WorkspaceDocument]. No session ID accepted in tool arguments. Store performs path/byte/count limits too. `validate_workspace_path(path)->str` rejects absolute, dot/dotdot, backslash, null, colon, encoded escapes and invalid paths. No filesystem backend.
- WorkspaceLimits(max_file_bytes=16384,max_workspace_bytes=65536,max_workspace_files=8).
- ToolPolicyContext(session_id,allowed_tools,permissions,limits:WorkspaceLimits); dispatcher constructor ToolDispatcher(registry).
- registry.definitions(allowed_tools:list[str])->list[dict] creates OpenAI function schemas for supported allowlisted tools.
- dispatcher.authorize(call,context)->AuthorizationDecision(allowed,code,message). Checks known tool, allowed ID, required permissions, input schema/path and sizes before execution. dispatcher.execute(call,context,store)->ToolExecutionOutcome(result:ToolResult,modified_file:WorkspaceDocument|null). Execute repeats authorization (no bypass). ToolResult.status completed|failed|unsupported|denied, content JSON safe public result. Reject unsupported tool calls, never shell/network/host access.
- No host sandbox claims. Logical workspace is PostgreSQL text rows scoped by session. Policy+database limits enforced before mutation, under session row lock. Snapshot modified files for evaluator input at submission.

## Backend public API

Keep /api prefix and existing public fields; additions backward-compatible.

- GET /api/runtime/options -> {default_profile:'mock'|'compatible', profiles:[{id,label,model,capabilities:{tools,system_messages,temperature,token_limit_parameter}}]}. Always mock; compatible only when baseURL+model configured. Do not expose URL/key/pricing secrets. Settings via PRAXIOJ_LLM_BASE_URL, PRAXIOJ_LLM_API_KEY, PRAXIOJ_LLM_MODEL, PRAXIOJ_DEFAULT_PROFILE=mock, PRAXIOJ_LLM_SUPPORTS_TOOLS, PRAXIOJ_LLM_SUPPORTS_SYSTEM, PRAXIOJ_LLM_SUPPORTS_TEMPERATURE, PRAXIOJ_LLM_TOKEN_PARAMETER, PRAXIOJ_LLM_TIMEOUT_SECONDS. Prices optional PRAXIOJ_PRICE_INPUT_PER_MILLION, PRAXIOJ_PRICE_OUTPUT_PER_MILLION, PRAXIOJ_PRICE_CURRENCY=USD. Explicit server config only, not request data.
- POST /api/sessions existing body + runtime_profile optional (select server profile only). Persist ModelConfig and safe profile capability/pricing snapshot. Enforce manifest AI policy, tool capability compatibility. Never store credentials/baseURL. Seed logical files from initial_resources under limits. SessionDetail adds runtime_profile, model_configuration, active_run_id:string|null, draft:string (default ''), latest_run:RunView|null. status active|submitted|ended. All owner scoped.
- POST /api/sessions/{id}/runs {content,request_id:UUID} ->202 RunView; same request_id+samecontent returns existing run; mismatched body409. One active run per session; conflicting new request409. Reserve/persist user turn and queued run transactionally, launch in-process async task. Persist history including assistant tool calls and tool results before next provider call. API reads expose message roles user/assistant/tool, tool_calls,tool_call_id.
- GET /api/runs/{id} ->RunView {id,session_id,request_id,status:queued|running|completed|failed|cancelled,error:{code,message}|null,created_at,finished_at}. GET /api/sessions/{id}/runs -> array RunView.
- POST /api/runs/{id}/cancel {} ->RunView; durable cancel_requested + cancel owned task; cancellation safe even if provider already billed, do not assert refund/exact usage. Polling exposes terminal state. Startup recovers interrupted runs as failed; no silent replay of remote calls. Shutdown cancels local tasks.
- GET /api/sessions/{id}/usage -> {model_calls,tool_calls,input_tokens,output_tokens,usage_complete,estimated,cost_estimate:number|null,currency:string|null,cost_estimate_complete,limits:{...}}. Counters reserve attempts (including failures); known tokens additive; null upstream values do not become exact zero. Show known subtotal when incomplete, estimates labeled. Optional token budget halts further requests if unknown.
- GET /api/sessions/{id}/files -> array {path,content,sha256,byte_size,revision}. No arbitrary host paths, no upload endpoint needed; tools modify only own scoped DB storage.
- PUT /api/sessions/{id}/draft {content} -> {content}; explicit UI Save draft, persists state. Can load a tool file into draft via UI then save.
- POST /api/sessions/{id}/end {} -> SessionDetail; reject while active run, set ended, trace lifecycle. Submit blocked while active run or ended; existing submission/evaluation routes stay and evaluation receives workspace artifact snapshots plus authorized trace.
- request timeouts must not lock DB across network; each provider call attempt durable with its ID and usage status. Bound tool loop by max_model_calls/max_tool_calls/max_run_seconds. Reject concurrent /messages legacy, /runs, submission, end appropriately.

## Trace, confidentiality, sequencing

Add EventType PROVIDER_CALL_STARTED, PROVIDER_CALL_COMPLETED, TOOL_CALL_AUTHORIZED, SESSION_STATE_CHANGED. Existing TOOL_CALL_REQUESTED/COMPLETED, ARTIFACT_UPDATED, ERROR used. Envelope add correlation_id:str|null and parent_event_id:str|null optional; schema stays1.0 additive. Run ID + provider call ID + tool call ID in resource_ids. Provider errors use safe code only, no upstream raw message.

Public trace: metadata/identifiers/status/usage, sanitized message/tool content; no raw HTTP body, endpoint URL, headers, credential or internal exception. Internal diagnostics via a separate structured logger with code/runID/status only (no raw exceptions/content), not a public endpoint. Do not serialize Settings containing secrets (repr=False). Scrub configured API key by exact match if reflected by provider and redact recognizable token patterns before storage. Free-form secret/PII detection remains best-effort and documented; no telemetry exports.

Sequence allocation remains transactional under session lock with DB uniqueness. Event source server only. Idempotent run requests do not replay provider/tool events. File writes are idempotent by run/tool-call identity before retry, and each call may execute once. Unknown or duplicate upstream tool call IDs in a run fail before re-execution.

## Verification

Maintain all56 ordinary M1 cases; preserve legacy trace7event flow. Two PG concurrency tests must run if Docker available. Add async run lifecycle, cancellation, idempotency, recovery, scoped files, permissions/limits, real local HTTP provider loop tests and frontend cases. Live-provider tests marked live_provider and require explicit PRAXIOJ_RUN_LIVE_TESTS=1 plus nonempty dedicated test config; otherwise skip. No real external calls in this task. Update docs to actual implementation; retain Apache files and personal hobby identity.
