"""Evaluation contracts and an allowlisted, deterministic built-in evaluator."""

from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field, JsonValue, model_validator

from praxioj.core import Artifact, DomainModel, content_digest
from praxioj.problems import ProblemManifest
from praxioj.tracing import TraceEnvelope


class SubmissionData(DomainModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=100_000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_content(self) -> "SubmissionData":
        if content_digest(self.content) != self.sha256:
            raise ValueError("Submission digest does not match its content")
        return self


class EvaluationInput(DomainModel):
    problem: ProblemManifest
    submission: SubmissionData
    artifacts: list[Artifact] = Field(default_factory=list)
    trace: list[TraceEnvelope] = Field(default_factory=list)
    configuration: dict[str, JsonValue] = Field(default_factory=dict)


class EvidenceReference(DomainModel):
    kind: Literal["submission", "trace", "artifact"]
    reference: str


class CriterionResult(DomainModel):
    id: str
    title: str
    score: float | None = Field(default=None, ge=0)
    maximum_score: float | None = Field(default=None, ge=0)
    passed: bool | None = None
    feedback: str
    evidence: list[EvidenceReference] = Field(default_factory=list)


class EvaluationResult(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    status: Literal["completed", "failed", "unsupported"]
    score: float | None = Field(default=None, ge=0)
    maximum_score: float | None = Field(default=None, ge=0)
    criteria: list[CriterionResult] = Field(default_factory=list)
    feedback: list[str] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    evaluator_id: str
    evaluator_version: str


class Evaluator(Protocol):
    def evaluate(self, request: EvaluationInput) -> EvaluationResult: ...


class EvaluationExecutor(Protocol):
    """Future worker boundary. External evaluators require an isolated implementation."""

    def execute(self, request: EvaluationInput) -> EvaluationResult: ...


class TextRubricEvaluator:
    """Small infrastructure example, not a measure of real problem-solving ability."""

    def evaluate(self, request: EvaluationInput) -> EvaluationResult:
        content = request.submission.content.casefold()
        evidence = [EvidenceReference(kind="submission", reference=request.submission.id)]
        criteria = []
        for definition in request.problem.evaluation.criteria:
            terms = definition.config["required_terms"]
            passed = all(term.casefold() in content for term in terms)
            criteria.append(CriterionResult(
                id=definition.id, title=definition.title,
                score=definition.max_score if passed else 0, maximum_score=definition.max_score,
                passed=passed,
                feedback="Criterion satisfied." if passed else "Criterion not satisfied; review the published description.",
                evidence=evidence,
            ))
        return EvaluationResult(
            status="completed", score=sum(item.score for item in criteria),
            maximum_score=sum(item.maximum_score for item in criteria), criteria=criteria,
            feedback=["Evaluated by a deterministic text rubric. This sample checks the infrastructure, not the quality of human–AI collaboration."],
            evidence=evidence, evaluator_id="builtin.text-rubric", evaluator_version="1.0.0",
        )


class EvaluationEngine:
    """Only explicitly compiled-in evaluators run in-process. No import path loading."""

    def __init__(self) -> None:
        self._trusted: dict[tuple[str, str], Evaluator] = {("builtin.text-rubric", "1.0.0"): TextRubricEvaluator()}

    def evaluate(self, request: EvaluationInput) -> EvaluationResult:
        spec = request.problem.evaluation
        evaluator = self._trusted.get((spec.evaluator_id, spec.evaluator_version))
        if evaluator is None:
            return EvaluationResult(status="unsupported", evaluator_id=spec.evaluator_id,
                                    evaluator_version=spec.evaluator_version,
                                    feedback=["This evaluator requires an execution backend that is not available in Milestone 1."])
        if len(request.submission.content) > request.problem.resource_limits.max_submission_chars:
            raise ValueError("Submission exceeds the problem limit")
        return evaluator.evaluate(request)


class UnavailableIsolatedExecutor:
    def execute(self, request: EvaluationInput) -> EvaluationResult:
        raise NotImplementedError("Isolated evaluator execution is not implemented in Milestone 1")
