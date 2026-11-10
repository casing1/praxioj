# AI Workspace setup

M3 retains the Mock and OpenAI-compatible providers from M2 and moves AI execution into a separate worker. The API authenticates the participant, checks policy and budgets, and persists a job; the worker claims it through PostgreSQL. The default `mock` profile makes no provider network requests. This remains a localhost development feature, not a production service or code sandbox.

## Accounts and workspace flow

Start the API, worker, and web using [local setup](local-setup.md), then register or sign in. Each new solve session belongs to that account. Login expiry requires signing in again; messages, drafts and completed work remain in the database. A different account cannot access the session by guessing its ID.

Three examples remain available:

- `release-plan`: the original foundation text-rubric flow.
- `workspace-plan`: constrained logical files, tool calling, saved drafts, and final-artifact evaluation.
- `evidence-plan`: the same workspace workflow with six explicit final-artifact and process-evidence criteria.

Select **Create a release plan with reviewable evidence**, create a session, and ask the Mock assistant to **save a release plan**. Inspect the tool request/result and `plan.txt`, load its content into the draft, save, and submit. The result shows criterion feedback and evidence references. These deterministic checks establish recorded actions, not a participant's understanding or general AI skill.

Authors and administrators use the role-gated author page to publish immutable manifest versions and review permitted evaluation metadata. A trusted local operator grants those roles to an existing account; there is no default administrator. See [authentication](authentication.md).

## Provider configuration

Configure **both the API and the worker** with matching server-side settings. The API advertises profiles and snapshots session policy; the worker makes the actual compatible-provider calls. Native Python does not load `.env` implicitly. Compose uses its optional root `.env` and shares the runtime environment between API/worker. That file is Git-ignored and excluded from the Docker build context. Never put credentials in `VITE_` variables, commands, screenshots, logs or repository files.

| Variable | Meaning/default |
| --- | --- |
| `PRAXIOJ_DEFAULT_PROFILE` | `mock`; optionally `compatible` when configured |
| `PRAXIOJ_LLM_BASE_URL` | API prefix, such as `http://127.0.0.1:18081/v1`; the adapter appends `/chat/completions` |
| `PRAXIOJ_LLM_MODEL` | Endpoint-specific model ID, including IDs containing `/` |
| `PRAXIOJ_LLM_API_KEY` | Optional server-only bearer credential; blank for keyless local servers |
| `PRAXIOJ_LLM_SUPPORTS_TOOLS` | `false`; enable only for models supporting function tools |
| `PRAXIOJ_LLM_SUPPORTS_SYSTEM` | `true` |
| `PRAXIOJ_LLM_SUPPORTS_TEMPERATURE` | `true`; false omits temperature |
| `PRAXIOJ_LLM_TOKEN_PARAMETER` | `max_tokens` or `max_completion_tokens` |
| `PRAXIOJ_LLM_TIMEOUT_SECONDS` | `30`, combined with problem request/run deadlines |
| `PRAXIOJ_PRICE_INPUT_PER_MILLION` | Blank: no input price estimate |
| `PRAXIOJ_PRICE_OUTPUT_PER_MILLION` | Blank: no output price estimate |
| `PRAXIOJ_PRICE_CURRENCY` | `USD`; informational three-letter currency |

Base URL and model must be supplied together. Mock remains available when the compatible profile is configured. Participants select a configured profile; they cannot submit endpoints, credentials or arbitrary model IDs. Each session pins model settings, capability flags and explicitly configured prices. Credentials stay in server configuration. Changing that configuration can make an existing session's profile unavailable; it does not silently fall back to Mock. Restart both processes after changing provider settings.

The adapter uses non-streaming Chat Completions and supports HTTPS endpoints. HTTP is restricted to localhost, loopback IP literals, RFC 1918 private IPv4 literals, IPv6 ULA literals, and `host.docker.internal`. It rejects link-local/metadata addresses, unspecified addresses, other HTTP hostnames, URL credentials, query strings and fragments. Redirects and environment proxies are disabled. Request/response bodies are bounded to 1 MiB; compressed responses are rejected before decompression. This is an operator-configured connection boundary, not an SSRF-proof network sandbox. Capabilities are explicit; unsupported requested features fail clearly. Responses API, multimodal input, provider-native tools, token streaming and arbitrary shell/network tools are not implemented.

## Credential-free HTTP demonstration

First install dependencies and start the native PostgreSQL setup from [local setup](local-setup.md). Stop any existing native API/worker processes before changing their settings. In a fixture terminal:

```sh
python3 scripts/compatible-fixture.py
```

The fixture binds only `127.0.0.1:18081`. It is deterministic protocol test data, not an LLM; its usage counts are synthetic. It needs no key and makes no internet or paid API call.

In the API terminal, from the repository root:

```sh
export DATABASE_URL='postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj'
export PRAXIOJ_ENV=development
export PRAXIOJ_LLM_BASE_URL=http://127.0.0.1:18081/v1
export PRAXIOJ_LLM_MODEL=fixture-model
export PRAXIOJ_LLM_API_KEY=
export PRAXIOJ_LLM_SUPPORTS_TOOLS=true
export PRAXIOJ_DEFAULT_PROFILE=mock
export PRAXIOJ_PRICE_INPUT_PER_MILLION=
export PRAXIOJ_PRICE_OUTPUT_PER_MILLION=
make migrate register
make api
```

In a separate worker terminal, export the same configuration explicitly:

```sh
export DATABASE_URL='postgresql+psycopg://praxioj:praxioj@127.0.0.1:5432/praxioj'
export PRAXIOJ_ENV=development
export PRAXIOJ_LLM_BASE_URL=http://127.0.0.1:18081/v1
export PRAXIOJ_LLM_MODEL=fixture-model
export PRAXIOJ_LLM_API_KEY=
export PRAXIOJ_LLM_SUPPORTS_TOOLS=true
export PRAXIOJ_DEFAULT_PROFILE=mock
export PRAXIOJ_PRICE_INPUT_PER_MILLION=
export PRAXIOJ_PRICE_OUTPUT_PER_MILLION=
make worker
```

Start `make web` in another terminal. Sign in, choose `evidence-plan` or `workspace-plan` and select the compatible profile. The fixture returns a tool call followed by a response to its stored tool result. Alternatively run:

```sh
python3 scripts/smoke-m2.py --profile compatible
python3 scripts/smoke-m3.py --profile compatible
python3 scripts/smoke-m3.py --profile compatible --base-url http://127.0.0.1:5173
```

These scripts register synthetic accounts and preserve local demonstration records. The smoke expects no configured prices. A container's `127.0.0.1` refers to that container, not the host fixture; the complete demonstration above therefore uses native API and worker processes. Do not broaden the fixture's loopback binding just to make it publicly reachable.

Restart the fixture with `--delay 5` or `--omit-usage` for cancellation and unknown-usage demonstrations. Missing usage remains unknown. Configured prices produce an estimate, never an exact bill. A failed or cancelled request may have consumed external resources even if no usage response arrived.

## Job lifecycle, recovery and retention

The UI polls persisted run/job status and tool activity; it does not stream tokens. A lost HTTP response can be retried with the same request UUID without creating a duplicate run. The job states are `PENDING`, `RUNNING`, `COMPLETED`, `FAILED` and `CANCELLED`; existing run states remain available for M2 clients.

Workers use leases, heartbeats and fencing checks before committing results. An API restart leaves healthy worker jobs intact. A dead worker's expired lease becomes an explicit failure when another worker reconciles it. Recovery does not automatically repeat a possibly billed provider call, and does not run while every worker is stopped. An explicit new attempt has a new request ID and consumes its own allowance. Cancellation prevents stale results/tool effects from committing locally; it cannot guarantee provider cancellation or a refund. See [persistent jobs](../architecture/persistent-jobs.md).

Trace has a bounded per-session expiry and a hash-chain checkpoint. The worker performs bounded cleanup; expired Trace reads fail even before deletion. Saved evaluations identify expired evidence references. Hash integrity is not independent tamper prevention. Account deletion requires cancelling active runs and removes private workspace data under the [retention policy](../architecture/trace-retention.md).

Ordinary automated tests use Mock, isolated storage and local HTTP fixtures. PostgreSQL integration cases exercise separate worker processes and crash recovery. The opt-in `live_provider` test is separate and skips unless all dedicated settings are provided: `PRAXIOJ_RUN_LIVE_TESTS=1`, `PRAXIOJ_TEST_LLM_BASE_URL`, `PRAXIOJ_TEST_LLM_MODEL`, and `PRAXIOJ_TEST_LLM_API_KEY`. Do not enable it during offline validation: it can contact a real provider and incur charges. Fixture results do not establish commercial model compatibility or reasoning quality.

Stop the fixture, Vite, API and worker with Ctrl-C when done. `docker compose down` preserves stored data; do not remove the volume to resolve a migration conflict.
