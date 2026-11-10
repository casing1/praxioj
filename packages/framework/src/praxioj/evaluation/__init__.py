"""Evaluation contracts and an allowlisted, deterministic built-in evaluator."""

from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field, JsonValue, StrictInt, model_validator

from praxioj.core import Artifact, DomainModel, Identifier, content_digest
from praxioj.problems import (ArtifactCriterion, ConstraintsCriterion, EventCriterion, FinalTextCriterion,
    ProblemManifest, ToolSuccessCriterion, UsageLimitCriterion, evidence_criterion)
from praxioj.tracing import EventType, TraceEnvelope, TraceIntegrityResult, verify_trace_chain


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


class ResourceUsageSnapshot(DomainModel):
    """Observed counts and nullable provider usage, not guessed billing totals."""
    user_messages: StrictInt | None = Field(default=None, ge=0, le=100_000_000)
    model_calls: StrictInt | None = Field(default=None, ge=0, le=100_000_000)
    tool_calls: StrictInt | None = Field(default=None, ge=0, le=100_000_000)
    input_tokens: StrictInt | None = Field(default=None, ge=0, le=100_000_000)
    output_tokens: StrictInt | None = Field(default=None, ge=0, le=100_000_000)
    usage_complete: bool = False
    estimated: bool = False

    def observed(self, metric: str) -> int | None:
        if metric in {"input_tokens", "output_tokens", "total_tokens"}:
            if not self.usage_complete or self.estimated:
                return None
            if metric == "total_tokens":
                if self.input_tokens is None or self.output_tokens is None:
                    return None
                return self.input_tokens + self.output_tokens
        return getattr(self, metric, None)


class ToolExecutionEvidence(DomainModel):
    call_id: Identifier
    run_id: str = Field(min_length=1, max_length=128)
    name: Identifier
    status: Literal["completed", "failed", "denied"]
    request_event_id: UUID
    authorization_event_id: UUID
    result_event_id: UUID


class EvaluationInput(DomainModel):
    problem: ProblemManifest
    submission: SubmissionData
    artifacts: list[Artifact] = Field(default_factory=list, max_length=100)
    trace: list[TraceEnvelope] = Field(default_factory=list, max_length=10_000)
    usage: ResourceUsageSnapshot = Field(default_factory=ResourceUsageSnapshot)
    tool_results: list[ToolExecutionEvidence] = Field(default_factory=list, max_length=100)
    trace_availability: Literal["available", "expired", "unavailable"] = "available"
    configuration: dict[str, JsonValue] = Field(default_factory=dict)


class EvidenceReference(DomainModel):
    kind: Literal["submission", "trace", "artifact", "usage"]
    reference: str


class CriterionResult(DomainModel):
    id: str
    title: str
    score: float | None = Field(default=None, ge=0)
    maximum_score: float | None = Field(default=None, ge=0)
    passed: bool | None = None
    feedback: str
    evidence: list[EvidenceReference] = Field(default_factory=list)
    status: Literal["completed", "failed", "unsupported"] = "completed"
    evaluator_version: str | None = None


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
    trace_integrity: TraceIntegrityResult | None = None


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
                evaluator_version="1.0.0",
                feedback="Criterion satisfied." if passed else "Criterion not satisfied; review the published description.",
                evidence=evidence,
            ))
        return EvaluationResult(
            status="completed", score=sum(item.score for item in criteria),
            maximum_score=sum(item.maximum_score for item in criteria), criteria=criteria,
            feedback=["Evaluated by a deterministic text rubric. This sample checks the infrastructure, not the quality of human–AI collaboration."],
            evidence=evidence, evaluator_id="builtin.text-rubric", evaluator_version="1.0.0",
        )


def tool_evidence_from_trace(trace: list[TraceEnvelope]) -> list[ToolExecutionEvidence]:
    """Project linked tool observations, never trust an unpaired result assertion.

    The caller must validate the complete chain and authorize its source. Provider
    call IDs may be reused in different runs, so matching is scoped to run and
    parent event IDs as well as the tool call ID.
    """
    by_id = {str(event.event_id): event for event in trace}
    result = []
    for event in trace:
        if event.event_type != EventType.TOOL_CALL_COMPLETED or event.source != "server":
            continue
        authorization = by_id.get(event.parent_event_id)
        request = by_id.get(authorization.parent_event_id) if authorization else None
        if (authorization is None or request is None
            or authorization.event_type != EventType.TOOL_CALL_AUTHORIZED
            or request.event_type != EventType.TOOL_CALL_REQUESTED
            or authorization.source != "server" or request.source != "server"
            or not request.sequence_number < authorization.sequence_number < event.sequence_number
            or len({request.session_id, authorization.session_id, event.session_id}) != 1):
            continue
        call_id, run_id = event.resource_ids.get("tool_call_id"), event.resource_ids.get("run_id")
        if not call_id or not run_id or any(
            item.resource_ids.get("tool_call_id") != call_id or item.resource_ids.get("run_id") != run_id
            for item in (request, authorization)
        ):
            continue
        status = event.payload.get("status")
        if event.payload.get("call_id") != call_id or status not in {"completed", "failed", "denied"}:
            continue
        # A successful result cannot turn a denied request into a successful use.
        if status == "completed" and authorization.payload.get("allowed") is not True:
            continue
        try:
            result.append(ToolExecutionEvidence(call_id=call_id, run_id=run_id,
                name=request.payload.get("name"), status=status, request_event_id=request.event_id,
                authorization_event_id=authorization.event_id, result_event_id=event.event_id))
        except ValueError:
            continue
    # Ambiguous duplicate completion records are not multiple successful calls.
    counts: dict[tuple[str, str], int] = {}
    for item in result:
        key = (item.run_id, item.call_id)
        counts[key] = counts.get(key, 0) + 1
    return [item for item in result if counts[(item.run_id, item.call_id)] == 1]


class EvidenceRubricEvaluator:
    """Explicit observable checks; no inference of participant understanding."""

    def evaluate(self, request: EvaluationInput) -> EvaluationResult:
        integrity = verify_trace_chain(request.trace)
        trusted_trace = (request.trace_availability == "available" and integrity.status == "verified"
                         and all(event.source == "server" for event in request.trace))
        # Evaluation only observes events preceding this immutable submission.
        # A caller cannot earn a pre-submission criterion with a later event.
        submission_events = [event for event in request.trace if event.event_type == EventType.SUBMISSION_CREATED
                             and event.resource_ids.get("submission_id") == request.submission.id]
        boundary = submission_events[0].sequence_number if len(submission_events) == 1 else None
        observed = [event for event in request.trace if boundary is not None and event.sequence_number < boundary]
        trusted_trace = trusted_trace and boundary is not None
        tool_results = tool_evidence_from_trace(observed) if trusted_trace else []
        # Supplied structured tool projections must agree with their trace source.
        # They can enrich other trusted evaluators but cannot forge this rubric.
        if request.tool_results:
            observed_results = {item.result_event_id: item for item in tool_results}
            if any(observed_results.get(item.result_event_id) != item for item in request.tool_results):
                trusted_trace = False
                tool_results = []

        criteria = []
        for definition in request.problem.evaluation.criteria:
            config = evidence_criterion(definition.config)
            passed: bool | None = None
            evidence: list[EvidenceReference] = []
            reason = "Required evidence is unavailable or could not be verified."
            if isinstance(config, FinalTextCriterion):
                passed = all(term.casefold() in request.submission.content.casefold() for term in config.required_terms)
                evidence = [EvidenceReference(kind="submission", reference=request.submission.id)]
            elif isinstance(config, ArtifactCriterion):
                matches = [artifact for artifact in request.artifacts if artifact.name == config.name
                           and (config.sha256 is None or artifact.sha256 == config.sha256)]
                passed = bool(matches)
                evidence = [EvidenceReference(kind="artifact", reference=item.id) for item in matches]
            elif isinstance(config, UsageLimitCriterion):
                amount = request.usage.observed(config.metric)
                if amount is not None:
                    passed = amount <= config.maximum
                    evidence = [EvidenceReference(kind="usage", reference=config.metric)]
                else:
                    reason = "This resource measurement is unavailable, incomplete, or estimated."
            elif trusted_trace:
                if isinstance(config, EventCriterion):
                    matches = [event for event in observed if event.event_type == config.event_type
                               and (config.actor is None or event.actor == config.actor)
                               and (config.event_name is None or event.payload.get("name") == config.event_name)]
                    passed = len(matches) >= config.min_count
                    evidence = [EvidenceReference(kind="trace", reference=str(event.event_id)) for event in matches]
                elif isinstance(config, ToolSuccessCriterion):
                    matches = [item for item in tool_results if item.name == config.name and item.status == "completed"]
                    passed = len(matches) >= config.min_count
                    evidence = [EvidenceReference(kind="trace", reference=str(event_id)) for item in matches
                                for event_id in (item.request_event_id, item.authorization_event_id, item.result_event_id)]
                elif isinstance(config, ConstraintsCriterion):
                    if config.rule == "no_runtime_errors":
                        violations = [event for event in observed if event.event_type == EventType.ERROR]
                    elif config.rule == "no_denied_tools":
                        violations = [event for event in observed if event.event_type == EventType.TOOL_CALL_AUTHORIZED
                                      and event.payload.get("allowed") is not True]
                    else:
                        allowed = set(request.problem.allowed_tools)
                        aliases = {"read_file": "workspace.read_file", "write_file": "workspace.write_file"}
                        violations = []
                        for event in observed:
                            if event.event_type != EventType.TOOL_CALL_REQUESTED:
                                continue
                            name = event.payload.get("name")
                            if not isinstance(name, str) or aliases.get(name, name) not in allowed:
                                violations.append(event)
                    passed = not violations
                    # A negative check cites the inspected sequence, including the
                    # submission boundary, rather than inventing a successful event.
                    references = violations or [*observed, submission_events[0]]
                    evidence = [EvidenceReference(kind="trace", reference=str(event.event_id)) for event in references]
            if passed is not None:
                reason = "Criterion satisfied." if passed else "Criterion not satisfied; review the published description."
            criteria.append(CriterionResult(id=definition.id, title=definition.title,
                score=(definition.max_score if passed else 0) if passed is not None else None,
                maximum_score=definition.max_score, passed=passed, feedback=reason, evidence=evidence,
                status="completed" if passed is not None else "unsupported", evaluator_version="1.0.0"))
        complete = all(item.status == "completed" for item in criteria)
        distinct = {(item.kind, item.reference): item for criterion in criteria for item in criterion.evidence}
        return EvaluationResult(status="completed" if complete else "unsupported",
            score=sum(item.score for item in criteria) if complete else None,
            maximum_score=sum(item.maximum_score for item in criteria), criteria=criteria,
            feedback=["Checks cover recorded actions and artifacts only. They do not establish understanding, judgment, or the quality of human–AI collaboration."],
            evidence=list(distinct.values()), evaluator_id="builtin.evidence-rubric", evaluator_version="1.0.0",
            trace_integrity=integrity)


class EvaluationEngine:
    """Only explicitly compiled-in evaluators run in-process. No import path loading."""

    def __init__(self) -> None:
        self._trusted: dict[tuple[str, str], Evaluator] = {
            ("builtin.text-rubric", "1.0.0"): TextRubricEvaluator(),
            ("builtin.evidence-rubric", "1.0.0"): EvidenceRubricEvaluator(),
        }

    def evaluate(self, request: EvaluationInput) -> EvaluationResult:
        spec = request.problem.evaluation
        evaluator = self._trusted.get((spec.evaluator_id, spec.evaluator_version))
        if evaluator is None:
            return EvaluationResult(status="unsupported", evaluator_id=spec.evaluator_id,
                                    evaluator_version=spec.evaluator_version,
                                    feedback=["This evaluator is not registered as a trusted built-in evaluator."])
        if len(request.submission.content) > request.problem.resource_limits.max_submission_chars:
            raise ValueError("Submission exceeds the problem limit")
        return evaluator.evaluate(request)


class UnavailableIsolatedExecutor:
    def execute(self, request: EvaluationInput) -> EvaluationResult:
        raise NotImplementedError("Isolated evaluator execution is not implemented in Milestone 1")
