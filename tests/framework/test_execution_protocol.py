"""Pure contracts and synthetic outputs, including adversarial result inputs."""
import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from praxioj.execution import (ArtifactDeclaration, CleanupResult, ExecutionArtifactMetadata, ExecutionCriterionDefinition,
    ExecutionOutputLimits, ExecutionPolicy, ExecutionRequest, ExecutionResourceLimits, ExecutionValidationError,
    MockJudgeBackend, MOCK_SUBMISSION_CONTENT, UnavailableExecutionBackend, build_mock_request,
    canonical_digest, canonical_json, parse_execution_request, policy_digest, result_output_digest,
    validate_artifact_path, validate_execution_result)
from praxioj.evaluation.execution import assess_synthetic_execution


@pytest.fixture
def execution_request():
    return build_mock_request(request_id=uuid4(), job_id=uuid4(), attempt_id=uuid4(), session_id=uuid4(),
        fence=1, submission_id=uuid4(), trace_head_sha256="a" * 64, trace_next_sequence_number=4,
        deadline=datetime.now(UTC) + timedelta(seconds=60),
        criteria=[{"id": "goal", "title": "Goal", "max_score": 30.0}, {"id": "risk", "title": "Risk", "max_score": 70.0}])


def output(execution_request, scenario="success"):
    return asyncio.run(MockJudgeBackend(scenario).execute(execution_request))


def test_request_and_result_round_trip_and_determinism(execution_request):
    assert parse_execution_request(canonical_json(execution_request)) == execution_request
    first = output(execution_request)
    assert output(execution_request) == first
    result = validate_execution_result(execution_request, json.dumps(first))
    assert result.status == "completed" and result.evaluation.score == 100
    assert result.resource_usage.cpu_seconds is None
    assert result.provenance == "synthetic_mock"
    assert result.cleanup == CleanupResult(status="not_required", reason="synthetic_no_resources")
    assert sha256(result.artifacts[0].content.encode()).hexdigest() == result.artifacts[0].metadata.sha256


def test_mock_assessment_is_explicit_and_does_not_confuse_execution_with_criteria(execution_request):
    result = output(execution_request, "evaluation_failed")
    assert result["status"] == "completed"
    assessment = assess_synthetic_execution(execution_request, result)
    assert assessment.evaluation.status == "completed" and assessment.evaluation.score == 0
    assert assessment.evaluation.evaluator_id == "mock.synthetic-rubric"
    assert not assessment.independent_execution_evidence and assessment.provenance == "synthetic_mock"
    assert [item.id for item in assessment.evaluation.criteria] == ["goal", "risk"]
    assert assess_synthetic_execution(execution_request, result).evaluation.id == assessment.evaluation.id


@pytest.mark.parametrize("scenario,status", [("failure", "failed"), ("cancelled", "cancelled"), ("timeout", "timed_out")])
def test_non_success_synthetic_fixtures_have_no_accepted_assessment(execution_request, scenario, status):
    result = validate_execution_result(execution_request, output(execution_request, scenario))
    assert result.status == status and result.evaluation is None and not result.artifacts
    assert assess_synthetic_execution(execution_request, result).evaluation.status == "unsupported"


@pytest.mark.parametrize("scenario", ["malformed", "oversized", "bad_digest"])
def test_mock_outputs_are_validated_as_untrusted(execution_request, scenario):
    with pytest.raises(ExecutionValidationError):
        validate_execution_result(execution_request, output(execution_request, scenario))


@pytest.mark.parametrize("field,value", [("protocol_version", "2.0"), ("fence", True), ("execution_type", "shell"),
    ("deadline", "2026-01-01T00:00:00"), ("extra_secret", "never accepted")])
def test_request_schema_rejects_unsupported_versions_types_and_authority(execution_request, field, value):
    data = execution_request.model_dump(mode="json")
    data[field] = value
    with pytest.raises(ExecutionValidationError):
        parse_execution_request(data)


def test_request_required_fields_hashes_fixture_and_duplicate_criteria(execution_request):
    data = execution_request.model_dump(mode="json")
    del data["job_id"]
    with pytest.raises(ExecutionValidationError):
        parse_execution_request(data)
    for field in ("input_digest", "policy_digest"):
        data = execution_request.model_dump(mode="json")
        data[field] = "0" * 64
        with pytest.raises(ExecutionValidationError):
            parse_execution_request(data)
    data = execution_request.model_dump(mode="json")
    data["input_snapshot"]["submission_content"] = "print('not a fixture')"
    with pytest.raises(ExecutionValidationError):
        parse_execution_request(data)
    with pytest.raises(ValidationError):
        ExecutionRequest(**{**execution_request.model_dump(), "criteria": execution_request.criteria + execution_request.criteria})


@pytest.mark.parametrize("kwargs", [{"cpu_seconds": 0}, {"memory_mb": 15}, {"pids": 0},
    {"wall_seconds": "60"}, {"network_policy": "allowlist"}, {"cpu_seconds": True}])
def test_resource_policy_is_strict_bounded_and_default_deny(kwargs):
    with pytest.raises(ValidationError):
        ExecutionResourceLimits(**kwargs)


@pytest.mark.parametrize("path", ["/a", "../a", "a/../b", "C:\\a", "a//b", "a/./b", "a%2fb", "caf\u00e9", "a\x00b", "CON.txt", "a.", "a\\b"])
def test_artifact_paths_reject_nonportable_or_ambiguous_keys(path):
    with pytest.raises(ValueError):
        validate_artifact_path(path)


@pytest.mark.parametrize("paths", [("a", "a"), ("A.txt", "a.txt"), ("a", "a/b"), ("A/b", "a")])
def test_duplicate_and_prefix_paths_are_rejected(paths):
    with pytest.raises(ValidationError):
        ExecutionPolicy(declared_artifacts=tuple(ArtifactDeclaration(id=f"id-{index}", relative_path=path) for index, path in enumerate(paths)))


def test_artifact_declaration_ids_and_policy_size_must_be_consistent():
    with pytest.raises(ValidationError):
        ExecutionPolicy(declared_artifacts=(ArtifactDeclaration(id="same", relative_path="a"), ArtifactDeclaration(id="same", relative_path="b")))
    with pytest.raises(ValidationError):
        ExecutionOutputLimits(max_artifact_bytes=100, max_total_artifact_bytes=99)
    with pytest.raises(ValidationError):
        ExecutionPolicy(allowed_operations=())
    with pytest.raises(ValidationError):
        ExecutionPolicy(policy_id="run-anything")


@pytest.mark.parametrize("field,value", [("request_id", str(uuid4())), ("job_id", str(uuid4())), ("attempt_id", str(uuid4())),
    ("fence", 2), ("input_digest", "0" * 64), ("policy_digest", "0" * 64), ("request_digest", "0" * 64), ("runtime_image_digest", "0" * 64),
    ("schema_version", "2.0"), ("provenance", "isolated")])
def test_result_binds_all_attempt_and_policy_fields(execution_request, field, value):
    data = output(execution_request)
    data[field] = value
    data["output_digest"] = result_output_digest(data)
    with pytest.raises(ExecutionValidationError):
        validate_execution_result(execution_request, data)


def test_result_rejects_undeclared_artifacts_scores_and_invalid_status(execution_request):
    for mutate in (
        lambda d: d["artifacts"][0]["metadata"].update(id="foreign"),
        lambda d: d["artifacts"][0]["metadata"].update(attempt_id=str(uuid4())),
        lambda d: d["artifacts"][0]["metadata"].update(relative_path="other.txt"),
        lambda d: d["evaluation"]["criteria"][0].update(id="foreign"),
        lambda d: d["evaluation"]["criteria"][0].update(score=31.0),
        lambda d: d["evaluation"]["criteria"][0].update(passed=False),
        lambda d: d["evaluation"]["criteria"][0].update(maximum_score=31.0),
        lambda d: d["evaluation"].update(score=99.0),
        lambda d: d.update(status="running"),
        lambda d: d.update(status="failed"),
        lambda d: d["cleanup"].update(status="completed", reason="runtime_reported"),
        lambda d: d["resource_usage"].update(cpu_seconds=1.0),
    ):
        data = output(execution_request)
        mutate(data)
        data["output_digest"] = result_output_digest(data)
        with pytest.raises(ExecutionValidationError):
            validate_execution_result(execution_request, data)


def test_artifact_bytes_size_count_and_output_digest_are_checked(execution_request):
    data = output(execution_request)
    data["artifacts"][0]["content"] += "changed"
    data["output_digest"] = result_output_digest(data)
    with pytest.raises(ExecutionValidationError):
        validate_execution_result(execution_request, data)
    data = output(execution_request)
    data["artifacts"] *= 2
    data["output_digest"] = result_output_digest(data)
    with pytest.raises(ExecutionValidationError):
        validate_execution_result(execution_request, data)
    data = output(execution_request)
    data["output_digest"] = "0" * 64
    with pytest.raises(ExecutionValidationError, match="output_digest_mismatch"):
        validate_execution_result(execution_request, data)
    policy = ExecutionPolicy(output_limits=ExecutionOutputLimits(max_artifact_bytes=1))
    small = execution_request.model_copy(update={"policy": policy, "policy_digest": policy_digest(policy)})
    with pytest.raises(ExecutionValidationError, match="artifact_binding_mismatch"):
        validate_execution_result(small, output(small))


@pytest.mark.parametrize("raw", ['{"schema_version":"1.0","schema_version":"2.0"}', '{"score":NaN}', '{"score":Infinity}', b'\xff'])
def test_json_duplicates_constants_and_encoding_rejected(execution_request, raw):
    with pytest.raises(ExecutionValidationError):
        validate_execution_result(execution_request, raw)


def test_input_result_size_structure_and_nonfinite_numbers_rejected(execution_request):
    for raw in (b" " * 65_537, {"nested": [[[[[[[[[[[[[[[[[[0]]]]]]]]]]]]]]]]]]}, {"x": [0] * 10_001}, {"x": "x" * 65_537}):
        with pytest.raises(ExecutionValidationError):
            validate_execution_result(execution_request, raw)
    data = output(execution_request)
    data["evaluation"]["criteria"][0]["score"] = float("nan")
    with pytest.raises(ExecutionValidationError):
        validate_execution_result(execution_request, data)


def test_frozen_nested_contracts_and_unsafe_model_copies_cannot_bypass_validation(execution_request):
    with pytest.raises(ValidationError):
        execution_request.policy.resource_limits.cpu_seconds = 100
    with pytest.raises(TypeError):
        execution_request.criteria[0] = execution_request.criteria[0]
    forged = execution_request.model_copy(update={"input_digest": "0" * 64})
    with pytest.raises(ExecutionValidationError):
        parse_execution_request(forged)
    result = validate_execution_result(execution_request, output(execution_request))
    forged_result = result.model_copy(update={"provenance": "isolated"})
    with pytest.raises(ExecutionValidationError):
        validate_execution_result(execution_request, forged_result)


def test_unknown_runtime_and_unavailable_backend_never_fall_back(execution_request, monkeypatch):
    unavailable = UnavailableExecutionBackend()
    monkeypatch.setattr(MockJudgeBackend, "execute", lambda *_: (_ for _ in ()).throw(AssertionError("No Mock fallback")))
    data = asyncio.run(unavailable.execute(execution_request))
    assert validate_execution_result(execution_request, data).status == "unavailable"
    assert unavailable.availability().status == "unavailable"
    assert not unavailable.capabilities.untrusted_code_execution
    future = execution_request.model_copy(update={"execution_type": "participant_code"})
    assert MockJudgeBackend().availability(future).status == "unavailable"
    unknown = execution_request.runtime_image.model_copy(update={"digest": "0" * 64})
    assert MockJudgeBackend().availability(execution_request.model_copy(update={"runtime_image": unknown})).status == "unavailable"


def test_framework_mock_has_no_process_network_or_filesystem_execution(execution_request, monkeypatch):
    import builtins
    import os
    import socket
    import subprocess
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Synthetic backend must not execute or read host resources")
    loop = asyncio.new_event_loop()
    try:
        with monkeypatch.context() as patch:
            for module, name in ((subprocess, "run"), (subprocess, "Popen"), (os, "system"), (socket, "socket"), (builtins, "open")):
                patch.setattr(module, name, forbidden)
            result = loop.run_until_complete(MockJudgeBackend().execute(execution_request))
            assert validate_execution_result(execution_request, result).status == "completed"
    finally:
        loop.close()


def test_result_validation_cannot_promote_an_unsupported_runtime(execution_request):
    unknown = execution_request.model_copy(update={"execution_type": "participant_code"})
    data = output(execution_request)
    from praxioj.execution import request_digest
    data["request_digest"] = request_digest(unknown)
    with pytest.raises(ExecutionValidationError, match="unsupported_execution_policy"):
        validate_execution_result(unknown, data)
    assert validate_execution_result(unknown, output(unknown)).status == "unavailable"


def test_combined_validation_and_assessment_uses_normalized_inputs(execution_request):
    from praxioj.evaluation.execution import validate_and_assess_synthetic_execution
    raw = output(execution_request)
    copied = execution_request.model_copy(update={"criteria": [item.model_dump(mode="json") for item in execution_request.criteria]})
    result, assessment = validate_and_assess_synthetic_execution(copied, raw)
    assert result.output_digest == assessment.output_digest
    assert assessment.evaluation.score == 100
    raw["evaluation"]["score"] = 9000.0
    with pytest.raises(ExecutionValidationError):
        validate_and_assess_synthetic_execution(execution_request, raw)


def test_wire_versions_are_required_and_json_must_be_utf8(execution_request):
    data = execution_request.model_dump(mode="json")
    del data["protocol_version"]
    with pytest.raises(ExecutionValidationError):
        parse_execution_request(data)
    for field in ("schema_version",):
        data = output(execution_request)
        del data[field]
        with pytest.raises(ExecutionValidationError):
            validate_execution_result(execution_request, data)
    data = output(execution_request)
    del data["artifacts"][0]["metadata"]["schema_version"]
    with pytest.raises(ExecutionValidationError):
        validate_execution_result(execution_request, data)
    with pytest.raises(ExecutionValidationError):
        validate_execution_result(execution_request, json.dumps(output(execution_request)).encode("utf-16"))


def test_empty_trace_checkpoint_uses_null_not_an_invented_digest(execution_request):
    from praxioj.execution import TraceCheckpoint
    empty = TraceCheckpoint(session_id=execution_request.session_id, head_sha256=None, next_sequence_number=1)
    assert empty.head_sha256 is None
    with pytest.raises(ValidationError):
        TraceCheckpoint(session_id=execution_request.session_id, head_sha256=None, next_sequence_number=2)
