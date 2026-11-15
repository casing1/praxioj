# PraxiOJ

[English](../../../README.md) · [한국어](README.md) · [문서 목차](index.md) · [변경 이력](CHANGELOG.md)

**AI-Assisted Online Judge Framework**
*사람과 AI의 협업을 평가하기 위한 오픈소스 프레임워크.*

PraxiOJ는 DoHyun Choi가 독립적으로 개발하는 개인 취미 오픈소스 프로젝트다. 대학·연구실·기업 과제와 무관하며 특정 기관의 공식 프로젝트이거나 후원을 받는 프로젝트가 아니다.

문제 작성자가 과제, 자료, 규칙과 평가 기준을 정의하고 참가자가 AI를 어떻게 활용하는지 평가할 기반을 제공한다. 기본 평가 대상은 AI와 함께 작업하는 사람이지만 계약은 다른 평가 목적의 확장도 고려한다.

**Framework**는 문제 Manifest, AI Provider Adapter, Trace, 평가와 실행 계약을 제공하는 독립 설치 가능한 Python 라이브러리다. **Platform**은 FastAPI REST API, PostgreSQL 영속성과 React 참가자 Workspace를 추가한다. Framework 코드는 웹 서버·ORM·Frontend를 가져오지 않는다.

M5는 버전 관리 실행 프로토콜, 별도 영속 Execution Broker, 단일 Attempt Capability, 엄격한 결과·Artifact 검증과 결정적인 Mock Judge를 제공한다. 기본 Judge는 Unavailable이다. 명시적인 로컬 테스트 설정에서 관리자 소유의 고정 합성 Fixture만 활성화하며 참가자 코드나 외부 Evaluator는 실행하지 않는다. 합성 평가는 기존 Evaluation 점수와 별도로 저장하고 Mock 출처를 명시한다.

M4의 계정·세션 제어, 공유 할당량, Worker 운영, 독립 유지보수, 데이터 내보내기·삭제와 격리된 PostgreSQL 복구 검증을 유지한다. AI Workspace는 Mock 및 서버 설정 OpenAI-compatible Provider, 제한된 논리 파일 Tool, Trace 무결성·보존과 예제 문제 3개를 제공한다. 기본 테스트에는 자격증명이 필요 없다.

개발 순서는 **Milestone → Issue → Feature Branch → PR → Validation → Squash Merge**다. [M6-A 수명주기·원격 Runner 기반](https://github.com/casing1/praxioj/milestone/1)과 별도의 [M6-B Linux 격리 검증](https://github.com/casing1/praxioj/milestone/2)은 향후 작업을 추적한다. 객체 생성은 구현 완료가 아니다. 이 Governance 단계에서 완료된 제품 기준선은 M5다.

> 개발 미리보기이며 localhost에서만 사용한다. 계정 세션과 역할 검사는 구현되어 있지만 운영 환경 보안 강화와 공개 배포 지원을 입증하지 않았다. 비밀정보나 민감한 개인정보를 입력하지 않는다.

## Docker Compose로 실행

Docker Engine을 시작한 뒤 저장소 루트에서 실행한다.

```sh
docker compose up --build -d --wait
```

**http://127.0.0.1:5173** 을 연다. API 문서는 **http://127.0.0.1:8000/api/docs**, 상태 확인은 **http://127.0.0.1:8000/api/health** 다. API 시작 전에 마이그레이션과 멱등 예제 등록을 수행한다. 호스트 포트는 Loopback에만 바인딩하며 기본 PostgreSQL 포트는 공개하지 않는다. API/Web의 Bridge Network는 참가자 실행 Sandbox가 아니다.

참가자 계정을 등록하고 로그인한다. 등록 응답은 계정 존재 여부를 드러내지 않는다. **Build a release plan in your AI workspace** 문제에서 Mock으로 세션을 시작하고 **Please save a release plan in plan.txt** 를 요청하면 결정적인 Tool 흐름을 확인할 수 있다. Tool 인가·결과와 저장 파일을 확인하고 최종 답안 초안에 불러와 저장·제출한다. 결과 화면은 기준별 점수·피드백·이벤트를 보여준다. Mock 응답은 사전 정의한 시연이며 실제 모델 추론이 아니다. 기존 **Plan a reliable release** 문제와 Tool·Artifact 이력을 평가하는 **Create a release plan with reviewable evidence** 문제도 제공한다.

**Account and data**에서 로그인 기록·할당량·암호 변경·암호 확인 후 내보내기·삭제를 이용한다. 암호 변경은 모든 로그인을 폐기한다. 큰 내보내기는 크기 제한 오류 이후에도 위치를 유지한 채 작은 페이지로 재개할 수 있다. 관리자용 **Operations** 화면은 별도로 제공하며 참가자 응답에 다른 계정·내부 Worker 정보를 노출하지 않는다. 네이티브·컨테이너 API는 전달 헤더 신뢰를 끈다. 로컬 Proxy 뒤의 클라이언트는 Proxy IP 제한을 공유한다.

Provider 설정과 자격증명 없는 로컬 HTTP Fixture는 [AI Workspace 설정](../../development/ai-workspace.md) (영문)을 참고한다. 기본 테스트에는 API Key나 유료 호출이 필요 없다.

```sh
docker compose logs api
docker compose down
```

`down` 후에도 명명 DB Volume은 유지된다. 네이티브 Python/Vite, 테스트와 선택적인 Loopback DB 포트는 [로컬 설정](../../development/local-setup.md) (영문)을 참고한다.

## 자원·데이터 운영

API와 Worker는 [.env.example](../../../.env.example)의 설정을 공유한다. 기본 계정별 활성 풀이 세션은 10개, 동시 실행은 2개이며 시스템 대기 Job은 100개, 실행 Job은 4개다. 일별 호출·Tool 예산과 보수적인 토큰 예약을 계정·문제·시스템에 적용한다. Provider 사용량을 모르면 미상으로 유지하며 예약량은 청구 측정값이 아니다. 세션 생성 시 논리 Artifact·Trace 용량을 예약한다. [할당량 정책](../../architecture/resource-quotas.md) (영문)에 한계와 절충을 설명한다.

AI Worker 없이 독립 유지보수를 실행할 수 있다.

```sh
docker compose exec api python -m praxioj_api.maintenance
python3 scripts/smoke-m4.py --base-url http://127.0.0.1:5173
```

M4 Smoke는 자신이 만든 합성 계정만 삭제한다. [백업·복구](../../development/backup-restore.md) (영문)는 PostgreSQL 도구와 저장소 외부의 비공개 파일, 새 격리 복구 DB를 사용한다. 애플리케이션은 Archive를 암호화하지 않으므로 별도 관리 암호화 Volume을 사용한다. 과거 백업의 복구 승격에는 권위 있는 삭제 원장이 필요하고 자동 승격은 제공하지 않는다. MFA·계정 복구·공개 배포도 지원하지 않는다.

## Framework 독립 사용

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

API 서버·DB·Frontend 없이 실행한다. [문제 형식](../../specifications/problem-format.md)과 [평가 계약](../../specifications/evaluation-contract.md) (영문)을 참고한다.

## 실행 계약 확인

독립 Framework에서 합성 요청을 검증하고 고정 Mock 응답을 기존 평가 결과 형식에 대응시킬 수 있다.

```python
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from praxioj.execution import MockJudgeBackend, build_mock_request
from praxioj.evaluation.execution import validate_and_assess_synthetic_execution

request = build_mock_request(
    request_id=uuid4(), job_id=uuid4(), attempt_id=uuid4(), session_id=uuid4(),
    fence=1, submission_id=uuid4(), trace_head_sha256=None, trace_next_sequence_number=1,
    deadline=datetime.now(UTC) + timedelta(seconds=60),
    criteria=[{"id": "fixture", "title": "Synthetic check", "max_score": 100.0}],
)
raw = asyncio.run(MockJudgeBackend().execute(request))
result, assessment = validate_and_assess_synthetic_execution(request, raw)
print(result.status, assessment.provenance, assessment.independent_execution_evidence)
# completed synthetic_mock False
```

빈 합성 Trace Checkpoint를 사용한다. Platform Broker는 저장된 소유자 Submission과 Trace를 별도로 검증한다. [실행 프로토콜](../../specifications/execution-protocol.md)과 [Broker 구조](../../architecture/execution-broker.md) (영문)에 권한·제한·수명주기·수용 기준을 설명한다.

기본 Compose Stack을 시작하고 Unavailable 동작을 확인한다. Smoke Script는 자체 합성 계정을 생성하고 기존 로컬 운영자 CLI로 그 계정에 관리자 역할을 부여한다.

```sh
python3 scripts/smoke-m5.py --expect-unavailable
PRAXIOJ_JUDGE_BACKEND=mock docker compose up -d --wait api
python3 scripts/smoke-m5.py --restart-api
# 테스트 후 기본 설정으로 복원:
docker compose up -d --wait api
```

API의 고정 합성 테스트 Harness만 활성화한다. Mock은 Platform 자격증명 없이 제한된 요청만 받으며 호스트 프로세스·네트워크·파일 수집·참가자 Import를 사용하지 않는다. OS 격리의 증거는 아니다. 실제 격리 Runner는 별도로 검토할 M6 작업이다.

## 저장소 구조

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
  src/praxioj/execution/  Versioned protocol and Mock; real execution unavailable
examples/problems/      Minimal versioned sample package
tests/                  Framework, API, migration, integration tests
docs/                   Architecture, specifications, development guides
docker/                 Same-origin web/API reverse proxy
scripts/                Startup, smoke checks, and synthetic benchmarks
```

## 검증

```sh
make install
make test
```

Python 테스트는 격리 DB·로컬 HTTP Fixture를 사용한다. Frontend 테스트는 Mock HTTP 응답으로 요청·상호작용을 검증한다. 외부 Provider 테스트는 명시적으로 Opt-in하지 않으면 Skip한다. PostgreSQL 통합, 합성 백업·복구와 전체 Stack Smoke는 별도 검증이다. 영문 [M5](../../development/validation-m5.md), [M4](../../development/validation-m4.md), [M3](../../development/validation-m3.md), [공개 준비](../../development/preflight-validation.md), [M2](../../development/validation-m2.md), [M1](../../development/validation.md) 기록과 [버전 선택](../../development/versions.md)을 참고한다.

## 설계와 후속 작업

- [아키텍처](../../architecture/overview.md), [모듈 경계](../../architecture/module-boundaries.md) (영문)
- [문제 형식](../../specifications/problem-format.md), [Trace](../../specifications/trace-events.md), [평가 계약](../../specifications/evaluation-contract.md) (영문)
- [Runtime·Tool](../../specifications/runtime-and-tools.md), [보안 경계](../../../SECURITY.md), [로드맵](../../development/roadmap.md) (영문)
- [인증](../../development/authentication.md), [Worker 운영](../../architecture/persistent-jobs.md), [데이터 관리](../../development/data-governance.md), [향후 Sandbox 설계](../../architecture/sandbox-architecture.md) (영문)
- [기여 안내](CONTRIBUTING.md)
- [문서 목차](index.md), [문서·번역 정책](development/documentation-policy.md), [변경 이력](CHANGELOG.md)
- [개발 절차](development/engineering-workflow.md): Issue 우선 추적, 실제 PR 메타데이터, README/CHANGELOG 검토, 영문·국문 일관성과 필수 최적화·보안 강화 단계

Copyright 2026 DoHyun Choi. PraxiOJ 원본 코드는 **Apache License, Version 2.0** (SPDX: `Apache-2.0`)이다. [LICENSE](../../../LICENSE), [NOTICE](../../../NOTICE)를 참고한다. 기여자는 자신의 기여물에 대한 저작권을 유지한다. 제3자 컴포넌트의 원래 라이선스·고지를 유지하며 [Web 고지](../../../THIRD_PARTY_NOTICES.txt)와 [라이선스·배포 안내](../../development/licensing.md) (영문)를 참고한다. [기여 안내](CONTRIBUTING.md)의 절차에 따라 외부 기여를 환영한다.
