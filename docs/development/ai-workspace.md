# AI Workspace setup

M2 is a localhost development feature. Its default profile is `mock`; it performs no network calls. Keep one API process (`uvicorn` without multiple workers). Runtime state is durable, but the task scheduler is in-process. On restart, interrupted runs fail explicitly and are not silently replayed.

## Provider configuration

The API reads server environment variables. Native Python does not load `.env` implicitly. Compose interpolates its optional root `.env`, which is ignored by Git and excluded from the Docker build context. Never use a `VITE_` variable for credentials. Do not paste secrets into commands, screenshots, diagnostics, or repository files.

| Variable | Meaning/default |
| --- | --- |
| `PRAXIOJ_DEFAULT_PROFILE` | `mock`; optionally `compatible` when configured |
| `PRAXIOJ_LLM_BASE_URL` | API prefix, e.g. local `http://127.0.0.1:18081/v1`; adapter appends `/chat/completions` |
| `PRAXIOJ_LLM_MODEL` | Endpoint-specific model ID, including IDs with `/` |
| `PRAXIOJ_LLM_API_KEY` | Optional server-only bearer credential; blank for keyless local servers |
| `PRAXIOJ_LLM_SUPPORTS_TOOLS` | `false`; enable only if that model supports function tools |
| `PRAXIOJ_LLM_SUPPORTS_SYSTEM` | `true` |
| `PRAXIOJ_LLM_SUPPORTS_TEMPERATURE` | `true`; false omits temperature |
| `PRAXIOJ_LLM_TOKEN_PARAMETER` | `max_tokens` or `max_completion_tokens` |
| `PRAXIOJ_LLM_TIMEOUT_SECONDS` | `30`; combined with problem request/run deadlines |
| `PRAXIOJ_PRICE_INPUT_PER_MILLION` | Blank: no input price estimate |
| `PRAXIOJ_PRICE_OUTPUT_PER_MILLION` | Blank: no output price estimate |
| `PRAXIOJ_PRICE_CURRENCY` | `USD`; informational three-letter currency |

Base URL and model must be configured together. Both profiles remain available when compatible is enabled. Participants select a server profile; they cannot send URLs, credentials, or arbitrary model IDs. A session pins model settings, capabilities, and configured prices. Endpoint credentials remain in the server configuration and are never serialized into session data. A server configuration change can make an existing profile unavailable; it does not silently switch that session to Mock.

The adapter uses non-streaming Chat Completions. It supports HTTPS endpoints. HTTP is allowed only for `localhost`, loopback IP literals, RFC 1918 private IPv4 literals, IPv6 ULA literals (`fc00::/7`), and `host.docker.internal`. Link-local/metadata addresses, unspecified addresses, other HTTP hostnames, URL credentials, query strings, and fragments are rejected. Redirects are not followed and environment proxies are disabled. Requests and responses are bounded to 1 MiB each. The adapter requests `Accept-Encoding: identity` and rejects compressed responses before decompression. This is not endpoint discovery or an SSRF-proof network sandbox. Only a trusted operator sets the endpoint. Provider support is explicit: tools, system messages, temperature, and output-token parameter. Unsupported requested features fail clearly. Responses API, multimodal input, provider-native tools, and streaming tokens are outside M2.

## Credential-free HTTP demonstration

Use the native API setup in [local setup](local-setup.md), then start the test fixture in another terminal:

```sh
python3 scripts/compatible-fixture.py
```

The fixture binds only `127.0.0.1:18081`. It is a deterministic HTTP test server, not an LLM. Its token counts are synthetic test data. No key or internet call is used.

Configure the native API process before starting it:

```sh
export PRAXIOJ_LLM_BASE_URL=http://127.0.0.1:18081/v1
export PRAXIOJ_LLM_MODEL=fixture-model
export PRAXIOJ_LLM_SUPPORTS_TOOLS=true
export PRAXIOJ_DEFAULT_PROFILE=mock
make migrate register
make api
```

In the UI, select **Build a release plan in your AI workspace** and the compatible profile. Request a release plan, inspect tool results and `plan.txt`, load the file into the draft, save, submit, and inspect the evaluation and trace. The fixture performs a tool request followed by a response to the stored tool result. Alternatively:

```sh
python3 scripts/smoke-m2.py
python3 scripts/smoke-m2.py --profile compatible
```

These checks create local sessions. Use `--base-url http://127.0.0.1:5173` to include the web proxy. The smoke assumes prices are unset. For a Docker API, a host endpoint may use `host.docker.internal`; loopback inside a container refers to that container. The fixture intentionally stays loopback-only, so the documented complete fixture demonstration uses a native API. Do not broaden its bind address for a public network.

`--delay 5` and `--omit-usage` on the fixture allow manual cancellation/unknown-usage demonstrations. Restart the fixture with the desired flags. Missing provider usage stays unknown. A failed/cancelled remote call may have consumed provider resources even if no usage was returned.

## Tests and recovery

Ordinary tests use Mock, FastAPI TestClient, and loopback HTTP fixtures; no credentials are required. Opt-in `live_provider` tests are separate and skip unless explicitly enabled with their dedicated test settings. Do not enable them during offline validation; they can contact the configured endpoint and incur charges. The opt-in variables are `PRAXIOJ_RUN_LIVE_TESTS=1`, `PRAXIOJ_TEST_LLM_BASE_URL`, `PRAXIOJ_TEST_LLM_MODEL`, and `PRAXIOJ_TEST_LLM_API_KEY`; all must be set. Run only that category with `python -m pytest -m live_provider`.

UI response status and tool activity use polling, not token streaming. A lost HTTP response can be retried with the same request UUID without creating a second run. A terminal failed run is visible; a deliberate new attempt consumes a new message/call allowance. Cancel requests stop local work and mark uncertain usage honestly; they cannot guarantee a refund or revoke a request already received by a provider.

Stop the fixture, Vite, and API with Ctrl-C when done. `docker compose down` preserves stored data. Do not delete the database volume to fix a migration conflict.
