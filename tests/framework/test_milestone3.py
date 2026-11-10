"""Deterministic evidence evaluation and portable trace integrity contracts."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from praxioj.core import Artifact, content_digest
from praxioj.evaluation import (EvaluationEngine, EvaluationInput, ResourceUsageSnapshot,
    SubmissionData, tool_evidence_from_trace)
from praxioj.problems import ProblemManifest, load_problem_package, manifest_digest, public_problem
from praxioj.tracing import (EventType, TraceEnvelope, compute_event_hash, seal_trace_event,
    verify_trace_chain)

ROOT = Path(__file__).resolve().parents[2]


def chain(*, allowed=True, tool_status="completed", include_artifact=True):
    events = []

    def append(kind, payload=None, parent=None, refs=None, actor="system"):
        event = TraceEnvelope(session_id="session-one", sequence_number=len(events) + 1,
            event_type=kind, payload=payload or {}, parent_event_id=parent,
            resource_ids=refs or {}, actor=actor)
        event = seal_trace_event(event, events[-1].event_hash if events else None)
        events.append(event)
        return event

    append(EventType.SESSION_STARTED)
    refs = {"run_id": "run-one", "tool_call_id": "call-one"}
    request = append(EventType.TOOL_CALL_REQUESTED, {"name": "write_file", "arguments": {}}, refs=refs,
                     actor="assistant")
    auth = append(EventType.TOOL_CALL_AUTHORIZED, {"allowed": allowed}, str(request.event_id), refs)
    append(EventType.TOOL_CALL_COMPLETED, {"call_id": "call-one", "status": tool_status}, str(auth.event_id), refs)
    if include_artifact:
        append(EventType.ARTIFACT_UPDATED, {"path": "plan.txt", "revision": 1}, refs=refs)
    append(EventType.SUBMISSION_CREATED, refs={"submission_id": "submission-one"}, actor="participant")
    return events


def reseal(events):
    result = []
    for event in events:
        result.append(seal_trace_event(event, result[-1].event_hash if result else None))
    return result


def evaluation_request(**changes):
    content = "Goal: release. Verification: tests. Risk: regression."
    defaults = dict(problem=load_problem_package(ROOT / "examples/problems/evidence-plan"),
        submission=SubmissionData(id="submission-one", content=content, sha256=content_digest(content)),
        artifacts=[Artifact(id="artifact-one", name="plan.txt", content=content, sha256=content_digest(content))],
        trace=chain(), usage=ResourceUsageSnapshot(model_calls=2, tool_calls=1, user_messages=1,
            input_tokens=20, output_tokens=30, usage_complete=True, estimated=True))
    defaults.update(changes)
    return EvaluationInput(**defaults)


def set_criteria(request, configs):
    data = request.problem.model_dump(mode="json")
    data["evaluation"]["criteria"] = [dict(id=f"rule-{i}", title=f"Rule {i}", max_score=10, config=config)
                                      for i, config in enumerate(configs)]
    request.problem = ProblemManifest.model_validate(data)
    return request


def test_trace_hash_chain_and_trusted_checkpoints():
    events = chain()
    result = verify_trace_chain(events, session_id="session-one", expected_head=events[-1].event_hash,
                                expected_next_sequence=len(events) + 1)
    assert result.status == "verified" and result.event_count == len(events)
    assert compute_event_hash(events[0]) == events[0].event_hash
    assert verify_trace_chain([event.model_dump(mode="json") for event in events]).status == "verified"
    suffix = verify_trace_chain(events[2:], session_id="session-one", anchor_hash=events[1].event_hash,
                                start_sequence=3, expected_head=events[-1].event_hash,
                                expected_next_sequence=len(events) + 1)
    assert suffix.status == "verified"
    assert verify_trace_chain(events[:-1], expected_next_sequence=len(events) + 1).reason == "checkpoint_length_mismatch"
    assert verify_trace_chain(events[:-1], expected_head=events[-1].event_hash).reason == "checkpoint_head_mismatch"


@pytest.mark.parametrize("field,value,reason", [
    ("payload", {"injected": "changed"}, "content_hash_mismatch"),
    ("actor", "administrator", "content_hash_mismatch"),
    ("resource_ids", {"run_id": "another-run"}, "content_hash_mismatch"),
    ("session_id", "another-session", "session_mismatch"),
    ("sequence_number", 99, "sequence_mismatch"),
    ("previous_hash", "f" * 64, "predecessor_mismatch"),
])
def test_trace_tampering_is_detected(field, value, reason):
    events = chain()
    events[2] = events[2].model_copy(update={field: value})
    assert verify_trace_chain(events).reason == reason


def test_trace_duplicate_reordered_and_legacy_events_are_not_verified():
    events = chain()
    events[2] = events[2].model_copy(update={"event_id": events[1].event_id})
    assert verify_trace_chain(events).reason == "duplicate_event_id"
    events = chain()
    events[1], events[2] = events[2], events[1]
    assert verify_trace_chain(events).reason == "sequence_mismatch"
    legacy = [TraceEnvelope(session_id="legacy", sequence_number=1, event_type=EventType.SESSION_STARTED)]
    assert verify_trace_chain(legacy).status == "unverified"
    assert verify_trace_chain([]).status == "empty"
    assert verify_trace_chain([], expected_next_sequence=2).status == "invalid"
    assert verify_trace_chain([{"invalid": True}]).reason == "invalid_envelope"


def test_sealing_is_detached_and_recomputed_chain_is_not_a_signature():
    original = TraceEnvelope(session_id="one", sequence_number=1, event_type=EventType.USER_MESSAGE,
                             payload={"content": "original"})
    sealed = seal_trace_event(original)
    original.payload["content"] = "changed"
    assert sealed.payload["content"] == "original"
    # A privileged writer can rewrite content and recompute every hash. The API's
    # storage/access controls and a separately protected checkpoint remain essential.
    rewritten = seal_trace_event(original)
    assert verify_trace_chain([rewritten]).status == "verified"
    assert verify_trace_chain([rewritten], expected_head=sealed.event_hash).status == "invalid"


def test_evidence_example_combines_final_artifact_trace_tools_and_usage():
    request = evaluation_request()
    result = EvaluationEngine().evaluate(request)
    assert result.status == "completed" and result.score == 100 and result.maximum_score == 100
    assert result.trace_integrity.status == "verified"
    assert all(criterion.status == "completed" and criterion.evaluator_version == "1.0.0" for criterion in result.criteria)
    assert {item.kind for item in result.evidence} == {"submission", "artifact", "trace", "usage"}
    assert "required_terms" not in result.model_dump_json()
    assert "understanding" in result.feedback[0]
    again = EvaluationEngine().evaluate(request)
    assert result.model_dump(exclude={"id"}) == again.model_dump(exclude={"id"})


def test_example_workspace_history_does_not_count_final_submission_artifact():
    # The Platform also records final submitted text as a participant artifact.
    # That automatic event is not evidence of a prior workspace file change.
    events = [
        TraceEnvelope(session_id="session-one", sequence_number=1, event_type=EventType.SESSION_STARTED),
        TraceEnvelope(session_id="session-one", sequence_number=2, event_type=EventType.ARTIFACT_UPDATED,
                      actor="participant", resource_ids={"submission_id": "submission-one"}),
        TraceEnvelope(session_id="session-one", sequence_number=3, event_type=EventType.SUBMISSION_CREATED,
                      actor="participant", resource_ids={"submission_id": "submission-one"}),
    ]
    result = EvaluationEngine().evaluate(evaluation_request(trace=reseal(events), artifacts=[]))
    history = next(criterion for criterion in result.criteria if criterion.id == "history")
    assert history.status == "completed" and history.score == 0 and history.passed is False


@pytest.mark.parametrize("allowed,status", [(False, "completed"), (False, "denied"), (True, "failed")])
def test_request_or_denial_or_failure_is_not_successful_tool_use(allowed, status):
    request = evaluation_request(trace=chain(allowed=allowed, tool_status=status))
    result = EvaluationEngine().evaluate(request)
    assert result.criteria[2].passed is False
    assert result.criteria[2].score == 0


@pytest.mark.parametrize("modification", ["orphan", "wrong_run", "wrong_call", "external"])
def test_tool_evidence_requires_matching_authorization_and_resource_context(modification):
    events = chain()
    if modification == "orphan":
        events[3].parent_event_id = str(events[0].event_id)
    elif modification == "wrong_run":
        events[3].resource_ids["run_id"] = "another-run"
    elif modification == "wrong_call":
        events[3].payload["call_id"] = "another-call"
    else:
        events[3].source = "external"
    request = evaluation_request(trace=reseal(events))
    result = EvaluationEngine().evaluate(request)
    assert result.criteria[2].passed is not True


def test_structured_tool_results_cannot_override_verified_trace():
    request = evaluation_request()
    projected = tool_evidence_from_trace(request.trace)
    assert len(projected) == 1 and projected[0].name == "write_file"
    request.tool_results = projected
    assert EvaluationEngine().evaluate(request).score == 100
    request.tool_results[0].name = "shell"
    result = EvaluationEngine().evaluate(request)
    assert result.status == "unsupported" and result.criteria[2].status == "unsupported"


def test_duplicate_tool_completion_is_ambiguous_and_not_double_counted():
    events = chain()
    duplicate = events[3].model_copy(deep=True)
    from uuid import uuid4
    duplicate.event_id = uuid4()
    duplicate.sequence_number = 5
    events.insert(4, duplicate)
    for index, event in enumerate(events):
        event.sequence_number = index + 1
    request = evaluation_request(trace=reseal(events))
    assert tool_evidence_from_trace(request.trace) == []
    assert EvaluationEngine().evaluate(request).criteria[2].score == 0


def test_malformed_tool_name_is_a_constraint_violation_not_an_expression():
    events = chain()
    events[1].payload["name"] = {"expression": "never evaluated"}
    request = set_criteria(evaluation_request(trace=reseal(events)),
                           [{"kind": "constraints", "rule": "allowed_tools_only"}])
    assert EvaluationEngine().evaluate(request).score == 0


@pytest.mark.parametrize("availability", ["expired", "unavailable"])
def test_expired_trace_preserves_independent_final_scores_without_fabricating_process_score(availability):
    request = evaluation_request(trace_availability=availability)
    result = EvaluationEngine().evaluate(request)
    assert result.status == "unsupported" and result.score is None
    assert result.criteria[0].score == 30 and result.criteria[1].score == 20
    assert result.criteria[2].score is None and result.criteria[2].passed is None


def test_tampered_legacy_or_missing_submission_boundary_does_not_earn_process_score():
    cases = [[], chain()[:-1], [event.model_copy(update={"event_hash": None}) for event in chain()]]
    changed = chain()
    changed[1].payload["name"] = "read_file"
    cases.append(changed)
    for events in cases:
        result = EvaluationEngine().evaluate(evaluation_request(trace=events))
        assert result.status == "unsupported" and result.criteria[2].passed is None


def test_events_after_submission_cannot_satisfy_pre_submission_criterion():
    events = chain(include_artifact=False)
    after = TraceEnvelope(session_id="session-one", sequence_number=len(events) + 1,
                          event_type=EventType.AUTHOR_EVENT, payload={"name": "validation.completed"})
    events.append(seal_trace_event(after, events[-1].event_hash))
    request = set_criteria(evaluation_request(trace=events),
        [{"kind": "event", "event_type": "AUTHOR_EVENT", "event_name": "validation.completed"}])
    result = EvaluationEngine().evaluate(request)
    assert result.status == "completed" and result.score == 0
    events[-2], events[-1] = events[-1], events[-2]
    for index, event in enumerate(events):
        event.sequence_number = index + 1
    request.trace = reseal(events)
    assert EvaluationEngine().evaluate(request).score == 10


@pytest.mark.parametrize("usage", [
    ResourceUsageSnapshot(),
    ResourceUsageSnapshot(input_tokens=0, output_tokens=0, usage_complete=False),
    ResourceUsageSnapshot(input_tokens=1, output_tokens=1, usage_complete=True, estimated=True),
])
def test_unknown_or_estimated_tokens_are_not_scored_as_exact_usage(usage):
    request = set_criteria(evaluation_request(usage=usage),
                           [{"kind": "usage_limit", "metric": "total_tokens", "maximum": 10}])
    result = EvaluationEngine().evaluate(request)
    assert result.status == "unsupported" and result.score is None and result.criteria[0].score is None


def test_known_usage_boundary_and_artifact_digest_criteria():
    request = set_criteria(evaluation_request(usage=ResourceUsageSnapshot(input_tokens=4, output_tokens=6,
                                                                        usage_complete=True)),
        [{"kind": "usage_limit", "metric": "total_tokens", "maximum": 10},
         {"kind": "artifact", "name": "plan.txt", "sha256": "0" * 64}])
    result = EvaluationEngine().evaluate(request)
    assert result.score == 10 and [criterion.passed for criterion in result.criteria] == [True, False]
    request.usage.output_tokens = 7
    assert EvaluationEngine().evaluate(request).score == 0


@pytest.mark.parametrize("rule,event,payload", [
    ("no_denied_tools", EventType.TOOL_CALL_AUTHORIZED, {"allowed": False}),
    ("no_runtime_errors", EventType.ERROR, {"code": "runtime_failed"}),
    ("allowed_tools_only", EventType.TOOL_CALL_REQUESTED, {"name": "shell"}),
])
def test_constraint_violations_produce_inspectable_evidence(rule, event, payload):
    request = set_criteria(evaluation_request(), [{"kind": "constraints", "rule": rule}])
    assert EvaluationEngine().evaluate(request).score == 10
    events = request.trace
    boundary = events.pop()
    added = TraceEnvelope(session_id="session-one", sequence_number=len(events) + 1,
                          event_type=event, payload=payload)
    events.append(added)
    boundary.sequence_number += 1
    events.append(boundary)
    request.trace = reseal(events)
    result = EvaluationEngine().evaluate(request)
    assert result.score == 0 and result.criteria[0].evidence[0].reference == str(added.event_id)


@pytest.mark.parametrize("config", [
    {"kind": "python", "code": "print('not executed')"},
    {"kind": "final_text", "required_terms": [""]},
    {"kind": "event", "event_type": "AUTHOR_EVENT", "min_count": 0},
    {"kind": "event", "event_type": "USER_MESSAGE", "event_name": "validation.completed"},
    {"kind": "tool_success", "name": "write_file", "min_count": True},
    {"kind": "artifact", "name": "../file"},
    {"kind": "usage_limit", "metric": "billed_cost", "maximum": 3},
    {"kind": "constraints", "rule": "no_runtime_errors", "expression": "ignored"},
])
def test_evidence_rule_configuration_is_bounded_and_declarative(config):
    with pytest.raises(ValidationError):
        set_criteria(evaluation_request(), [config])


def test_retention_bounds_public_projection_and_legacy_digest():
    manifest = load_problem_package(ROOT / "examples/problems/release-plan")
    assert manifest.trace_retention_days is None
    assert manifest_digest(manifest) == "0c5425eba5f6b5a79c67d5471d80a341497bce7555c2820f59f7985fc4e2e32c"
    workspace = load_problem_package(ROOT / "examples/problems/workspace-plan")
    assert manifest_digest(workspace) == "f0b03cb83b19350e7e69d056be2ea9ca78cacb90138335f2cae26358a60420be"
    original = manifest_digest(manifest)
    manifest.trace_retention_days = 30
    assert manifest_digest(manifest) != original
    assert public_problem(manifest)["trace_retention_days"] == 30
    for value in (0, 91, True, "30"):
        data = manifest.model_dump()
        data["trace_retention_days"] = value
        with pytest.raises(ValidationError):
            ProblemManifest.model_validate(data)
    evidence = load_problem_package(ROOT / "examples/problems/evidence-plan")
    public = public_problem(evidence)
    assert public["evaluation"]["criteria"][0].get("config") is None
