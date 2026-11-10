# Security boundaries

PraxiOJ Milestone 2 is a localhost development preview, not a production service. `PRAXIOJ_ENV` accepts only `development` and `test`. Compose publishes API/web ports on `127.0.0.1`, keeps PostgreSQL on an internal backend network, and leaves the database unpublished unless the optional native-development override is used. API/web share a separate bridge network so Docker can publish their loopback ports. The native-development override also attaches the database to this bridge for its loopback port. API/web containers can initiate outbound network requests; Compose networking is not a contestant sandbox. Run the native API on `127.0.0.1`. These deployment controls are required; the application host allowlist alone does not prevent access through a misconfigured proxy or tunnel.

## Implemented boundaries

- Strict Pydantic manifests validate supported fields. Directory registration reads the expected manifest only; it does not import code or dereference resource file paths. Resources remain inline text and are copied into bounded session-local database files.
- The API invokes only the trusted built-in evaluation registry. A manifest cannot name a module to import. Execution APIs explicitly report unavailable functionality.
- A random, server-issued HttpOnly, SameSite=Strict cookie identifies one browser-local participant. The database stores a token hash. Session, run, usage, file, draft, trace, and evaluation operations check ownership; client-supplied user IDs are not credentials.
- State-changing requests with an Origin header must come from the allowed localhost origins. Hostnames are restricted. The React UI renders participant and assistant text as text, not HTML.
- Problem API responses use an explicit public projection. Private evaluator configuration is excluded. Trace retrieval is limited to the session owner.
- Versioned manifests and immutable submissions use content hashes. Session mutations are transactional; PostgreSQL row locks serialize updates and trace sequence allocation.
- Provider endpoints/credentials are server-only. Participants choose a configured profile, never an arbitrary URL/key. HTTPX ignores proxy environment settings and redirects; total deadlines and body bounds limit requests. Explicit capability flags prevent unsupported features from silently being sent.
- Logical read/write tools validate strict inputs, relative paths, allowlists, required permissions, file sizes/counts, and aggregate bytes. Their store is bound to one session. There are no shell, network, host filesystem, or code-execution tools.
- User messages, model/tool attempts, provider duration, run duration, and logical workspace resources are bounded. Optional total-token limits rely on reported usage and fail closed on unknown usage; an in-flight call can overshoot the observed cap.
- New text persistence and public traces scrub the configured provider key and recognized sensitive keys/token patterns. Provider raw error bodies, headers, URLs, and internal exceptions are omitted. Internal runtime diagnostics record safe codes and operation IDs separately. This is best-effort filtering, not complete arbitrary-secret/PII detection.

## Known limitations

The development cookie is a bearer capability, not a verified login. Anyone using the same browser profile shares its local identity; deleting the cookie loses access to that browser's sessions. The user model reserves administrator, author, and participant roles, but only the local participant flow is exposed. There are no administrator/author role checks, account recovery, cross-device identity, HTTPS/session rotation, or production abuse controls. The development cookie expires after seven days; it is not renewable authentication. Author registration is a local operator CLI, not a participant API.

Conversations, drafts, tool content, and submissions can still contain unrecognized sensitive text; historical M1 records are not retroactively redacted. Do not paste secrets. There is no retention scheduler, encryption-at-rest setup, complete audit policy, or secret vault. Optional provider credentials are held in server configuration only. Environment-based configuration is a development mechanism, not a production secret-management system. Do not print environment variables or expanded Compose configuration into public logs.

Event observation does not expose a model's private chain of thought and does not guarantee replay of future nondeterministic AI runs. No model-generated text is interpreted as a shell command or elevated instruction.

There is no untrusted execution sandbox, external evaluator runner, distributed Judge Worker, or network-isolated contestant workspace. The tool dispatcher runs only explicitly registered trusted logical-file handlers. It does not isolate arbitrary code. Runs require one API process; multiple workers, global quotas, and distributed leases are not supported. Containerizing the web stack does not create these facilities. A production deployment must first implement real authentication/authorization, stronger request and resource controls, protected secrets, and isolated evaluation workers.

## Reporting

GitHub Private Vulnerability Reporting is enabled for this repository. Use [Report a vulnerability](https://github.com/casing1/praxioj/security/advisories/new) to send a private report to the maintainer. Include affected versions, prerequisites, impact, and a minimal reproduction using synthetic data. Do not include live credentials, participant data, or private submissions. Keep security details out of public issues while the report is being assessed. Public repository publication does not authorize public deployment.
