"""Run from the repository root: python examples/standalone.py (framework only)."""

import asyncio
from pathlib import Path

from praxioj.core import content_digest
from praxioj.evaluation import EvaluationEngine, EvaluationInput, SubmissionData
from praxioj.problems import load_problem_package
from praxioj.runtime import AIRuntime, Message, MockProvider, ModelConfig


async def main() -> None:
    problem = load_problem_package(Path(__file__).parent / "problems" / "release-plan")
    response = await AIRuntime(MockProvider()).respond(
        [Message(role="user", content="Help me plan this release.")],
        ModelConfig(), problem.resource_limits.max_messages,
    )
    print(response.content)
    content = "Goal: release a usable framework. Verification: run the tests. Risk: missing setup steps; rehearse a clean install."
    result = EvaluationEngine().evaluate(EvaluationInput(
        problem=problem,
        submission=SubmissionData(id="standalone-submission", content=content, sha256=content_digest(content)),
    ))
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
