# PraxiOJ

**AI-Assisted Online Judge Framework**  
*An open-source framework for evaluating human–AI collaboration.*

PraxiOJ is an independent personal hobby open-source project developed by DoHyun Choi. It is unrelated to university, research-laboratory, or corporate assignments and is not an official project of, or endorsed by, any university, laboratory, company, or other institution.

PraxiOJ provides the infrastructure for authors to define problems and evaluate how participants use AI to solve them. Authors own the tasks, resources, rules, and evaluation criteria. The default subject of evaluation is the person working with AI; the contracts also leave room for other evaluation purposes.

The **Framework** is an independently installable Python library for problem manifests, AI provider adapters, traces, evaluation, and execution contracts. The **Platform** adds a FastAPI REST API, PostgreSQL persistence, and a React participant workspace. Framework code never imports the web server, ORM, or frontend.

Milestone 3 adds account authentication, backend roles, a PostgreSQL job queue with a separate worker, bounded trace retention, hash verification, and evidence-based evaluation. It preserves the AI Workspace: persistent conversation and draft, asynchronous model runs, cancellation, permission-checked logical file tools, usage accounting, and ordered traces. The default Mock Provider needs no credentials. A server-configured OpenAI-compatible Chat Completions adapter can connect to hosted APIs or local LLM endpoints. Three sample problems demonstrate text and trace-based rubrics. There is no arbitrary code execution, terminal, security sandbox, or Judge Worker.

> Development preview only. Keep it on localhost. Account sessions and role checks are implemented, but production hardening and public deployment support are not established. Do not enter secrets or sensitive personal data.

## Run with Docker Compose

Start your Docker engine, then from the repository root:

```sh
docker compose up --build -d --wait
```

Open **http://127.0.0.1:5173**. API documentation is at **http://127.0.0.1:8000/api/docs**; health is at **http://127.0.0.1:8000/api/health**. Migrations and idempotent sample registration run before the API starts. Host ports bind to loopback only. PostgreSQL has no published port in this default setup. API/web use a bridge network for loopback port publishing; this does not provide a contestant execution sandbox.

Register a participant account, then select **Build a release plan in your AI workspace**, choose Mock, and start a session. Ask **Please save a release plan in plan.txt** to exercise the deterministic tool flow. Inspect tool authorization/results and the saved file, load it into the final-answer draft, save, and submit. The result screen displays criterion scores, feedback, and recorded events. Mock replies are predefined demonstrations, not actual model inference. The original **Plan a reliable release** problem remains available. **Create a release plan with reviewable evidence** additionally evaluates the permitted tool and artifact history.

See [AI Workspace setup](docs/development/ai-workspace.md) for provider configuration and a credential-free local HTTP fixture. No API key or paid call is needed for normal tests.

```sh
docker compose logs api
docker compose down
```

The named database volume survives `down`. See [local setup](docs/development/local-setup.md) for native Python/Vite development, tests, and an optional loopback database port.

## Use the Framework independently

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e packages/framework
```

```python
from hashlib import sha256
from praxioj.problems import load_problem_package
from praxioj.evaluation import EvaluationEngine, EvaluationInput, SubmissionData

problem = load_problem_package("examples/problems/release-plan")
text = "Goal: ship a small release. Verification: run checks. Risk: prepare a rollback."
submission = SubmissionData(id="demo", content=text, sha256=sha256(text.encode()).hexdigest())
result = EvaluationEngine().evaluate(EvaluationInput(problem=problem, submission=submission))
print(result.model_dump_json(indent=2))
```

No API server, database, or frontend is required for this example. See [problem format](docs/specifications/problem-format.md) to create a new manifest and [evaluation contract](docs/specifications/evaluation-contract.md) for evaluator extension boundaries.

## Repository

```text
apps/api/                FastAPI, SQLAlchemy models, registration CLI, Alembic
apps/web/                React + TypeScript + Vite participant UI and Vitest tests
packages/framework/     Installable praxioj package
  src/praxioj/core/       Shared domain contracts
  src/praxioj/problems/   Problem SDK, manifest validation, safe directory loader
  src/praxioj/runtime/    Provider protocol, mock/compatible adapters, capabilities
  src/praxioj/tools/      Permission checks, schemas, bounded logical file tools
  src/praxioj/tracing/    Event envelope, collector contract, redaction
  src/praxioj/evaluation/ Evaluation contracts and trusted deterministic evaluator
  src/praxioj/execution/  Execution interface; no sandbox implementation
examples/problems/      Minimal versioned sample package
tests/                  Framework, API, migration, integration tests
docs/                   Architecture, specifications, development guides
docker/                 Same-origin web/API reverse proxy
scripts/                Container API startup
```

## Validate

```sh
make install
make test
```

Python tests use isolated databases and local HTTP fixtures; frontend tests exercise requests and interactions with mocked HTTP responses. External provider tests require explicit opt-in and otherwise skip. PostgreSQL integration and full-stack smoke checks are separate checks; see the [M3 validation record](docs/development/validation-m3.md), [Preflight report](docs/development/preflight-validation.md), historical [M2 validation record](docs/development/validation-m2.md) and historical [M1 validation](docs/development/validation.md). See [version choices](docs/development/versions.md) for dependency pins.

## Design and next steps

- [Architecture](docs/architecture/overview.md) and [module boundaries](docs/architecture/module-boundaries.md)
- [Problem format](docs/specifications/problem-format.md), [trace events](docs/specifications/trace-events.md), [evaluation contract](docs/specifications/evaluation-contract.md)
- [Runtime and tools](docs/specifications/runtime-and-tools.md), [security boundaries](SECURITY.md), and [roadmap](docs/development/roadmap.md)
- [Contributing](CONTRIBUTING.md)
- [Engineering workflow](docs/development/engineering-workflow.md): PR writing, per-change README review, and mandatory optimization/hardening gates

Copyright 2026 DoHyun Choi. PraxiOJ's original code is licensed under the **Apache License, Version 2.0** (SPDX: `Apache-2.0`); see [LICENSE](LICENSE) and [NOTICE](NOTICE). Contributors retain copyright in their own contributions. Third-party components retain their original licenses and notices; see [third-party web notices](THIRD_PARTY_NOTICES.txt) and the [licensing and distribution notes](docs/development/licensing.md). External contributions are welcome under the process in [CONTRIBUTING.md](CONTRIBUTING.md).
