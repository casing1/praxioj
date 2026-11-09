# Problem package formats 1.0 and 1.1

A package is a directory with a UTF-8 `manifest.json`. The first format supports inline text resources, text submissions, and a declarative rubric. It does not read a path supplied inside the manifest, unpack archives, or import Python. See the runnable [sample](../../examples/problems/release-plan/manifest.json) for the authoritative full example.

```json
{
  "schema_version": "1.0",
  "id": "release-plan",
  "version": "1.0.0",
  "title": "Plan a small release",
  "description": "Use the internal AI workspace to draft a release plan.",
  "category": "collaboration",
  "difficulty": "introductory",
  "initial_resources": [],
  "allowed_ai_capabilities": ["chat"],
  "allowed_tools": [],
  "resource_limits": {
    "max_messages": 10,
    "max_message_chars": 4000,
    "max_submission_chars": 20000
  },
  "submission": {
    "kind": "text",
    "instructions": "Submit a release plan with a goal, verification, and risk."
  },
  "evaluation": {
    "evaluator_id": "builtin.text-rubric",
    "evaluator_version": "1.0.0",
    "criteria": [
      {
        "id": "goal",
        "title": "Clear goal",
        "description": "State a release goal.",
        "max_score": 1,
        "config": {"required_terms": ["goal"]}
      }
    ]
  }
}
```

The SDK rejects malformed manifests and unsupported fields instead of silently accepting spelling mistakes. Identifiers and stable three-part versions (`major.minor.patch`, no prerelease/build suffix) are validated. Limits are positive bounded values. A criterion has an identifier, public wording and maximum score, plus private evaluator configuration. Initial resources contain `name`, `content`, and `media_type`; M1 provides no resource downloads or filesystem paths. The directory loader accepts a manifest of at most 1 MiB. The API also enforces a global 128 KiB JSON request-body limit, so a large multi-byte submission can hit that byte ceiling before its configured character limit. The schema implementation is the source of truth for exact field length/range limits.

## Validate and register

```python
from praxioj.problems import load_problem_package, manifest_digest, public_problem

problem = load_problem_package("examples/problems/release-plan")
print(problem.id, problem.version, manifest_digest(problem))
print(public_problem(problem))
```

For a running, migrated platform database:

```sh
python -m praxioj_api.cli register examples/problems/release-plan
```

Registration is an operator CLI, not an unauthenticated author endpoint. It stores the validated canonical manifest and its SHA-256 digest. A repeated registration with the same ID, version and digest succeeds without producing another version. Changing any manifest content requires a new version; an existing `(id, version)` cannot be overwritten. Existing sessions continue using their pinned `ProblemVersion`. The list/detail default is the most recently registered version, not a semantic-version sort; pass the version explicitly when starting a session.

The loader requires the expected regular manifest file and enforces package/size boundaries. It does not turn an arbitrary manifest value into a host filesystem read. Rejection of traversal/symlink misuse is tested. Treat package directories as untrusted input even though a local operator chooses the directory.

## Public and private fields

The participant API returns an explicit public projection: identity/version, descriptive fields, inline resources, declared capabilities/tools, limits, submission instructions, and public criterion labels/weights. It never serializes the complete private manifest as its response.

`evaluation.criteria[*].config` stays server-side. The demo rubric uses `required_terms`; real private tests and other secrets belong in protected author/worker storage in a later milestone. Feedback reports criterion outcomes without revealing hidden required terms. Redaction is not a substitute for this public/private separation.

## Extension policy

A new problem using a supported rubric requires no platform code changes. A custom evaluator can be represented by its versioned identity in the contracts, but unsupported implementations are explicitly unavailable. A module path in a manifest must not be dynamically imported. Python evaluator distribution and execution will be added only with a worker-side trust and isolation model.

Bump `version` whenever resources, rules, limits, or grading configuration change. Bump `schema_version` only for a format change; schema evolution must include a migration/compatibility policy before older versions are removed.

## Format 1.1: AI Workspace policies

The [workspace sample](../../examples/problems/workspace-plan/manifest.json) uses schema `1.1`. Original schema `1.0` packages remain accepted. The canonical digest omits newly added fields when they equal their compatibility defaults for schema 1.0; this preserves existing registered hashes. Non-default new policies still affect the digest. The original `release-plan/1.0.0` package is unchanged.

- `ai_policy.allowed_providers` and `allowed_models` restrict the configured profile/model. Empty arrays allow operator-configured profiles. `max_output_tokens` bounds completion output; `allow_temperature` controls its use.
- `allowed_ai_capabilities` includes `chat` and optionally `tool_calling`.
- `allowed_tools` uses registry IDs (`workspace.read_file`, `workspace.write_file`). `tool_permissions` separately grants `workspace:read` and/or `workspace:write`; naming a tool alone does not authorize it.
- Resource limits add `max_model_calls`, `max_tool_calls`, optional `max_total_tokens`, `request_timeout_seconds`, `max_run_seconds`, `max_file_bytes`, `max_workspace_bytes`, and `max_workspace_files`. See [runtime and tools](runtime-and-tools.md) for observed-token limits and unknown usage.

Inline resources become session-local logical files when a session starts and must satisfy path/size/count limits. Runtime model configuration, provider capabilities, and optional prices are snapshotted per session. API keys and endpoint addresses never enter the manifest or public projection. Unsupported provider/tool combinations fail before work; a model request cannot grant itself permissions.
