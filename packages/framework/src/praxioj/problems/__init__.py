"""Declarative, versioned problem packages. Loading never imports Python code."""

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from praxioj.core import DomainModel, Identifier, Version

MAX_MANIFEST_BYTES = 1_048_576


class InitialResource(DomainModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[^/\\]+$")
    content: str = Field(max_length=100_000)
    media_type: Literal["text/plain", "application/json", "text/markdown"] = "text/plain"

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        if value in {".", ".."} or "\x00" in value:
            raise ValueError("Resource name must be a simple label, not a path")
        return value


class ResourceLimits(DomainModel):
    max_messages: int = Field(default=20, ge=1, le=100)
    max_message_chars: int = Field(default=4000, ge=1, le=20_000)
    max_submission_chars: int = Field(default=20_000, ge=1, le=100_000)
    max_model_calls: int = Field(default=30, ge=1, le=100)
    max_tool_calls: int = Field(default=20, ge=0, le=100)
    max_total_tokens: int | None = Field(default=None, ge=1, le=10_000_000)
    request_timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_run_seconds: int = Field(default=90, ge=1, le=300)
    max_file_bytes: int = Field(default=16_384, ge=1, le=100_000)
    max_workspace_bytes: int = Field(default=65_536, ge=1, le=1_048_576)
    max_workspace_files: int = Field(default=8, ge=1, le=100)


class AIPolicy(DomainModel):
    allowed_providers: list[Identifier] = Field(default_factory=list, max_length=50)
    allowed_models: list[str] = Field(default_factory=list, max_length=100)
    max_output_tokens: int = Field(default=1024, ge=1, le=32768)
    allow_temperature: bool = True


class SubmissionSpecification(DomainModel):
    kind: Literal["text"] = "text"
    instructions: str = Field(min_length=1, max_length=10_000)


class CriterionDefinition(DomainModel):
    id: Identifier
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    max_score: float = Field(gt=0, le=1_000_000)
    config: dict[str, JsonValue] = Field(default_factory=dict)


class EvaluationSpecification(DomainModel):
    evaluator_id: Identifier
    evaluator_version: Version
    criteria: list[CriterionDefinition] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_criteria(self) -> "EvaluationSpecification":
        ids = [criterion.id for criterion in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("Criterion IDs must be unique")
        if self.evaluator_id == "builtin.text-rubric":
            for criterion in self.criteria:
                terms = criterion.config.get("required_terms")
                if set(criterion.config) != {"required_terms"} or not isinstance(terms, list):
                    raise ValueError("Text rubric requires only a required_terms list")
                if not 1 <= len(terms) <= 100 or any(
                    not isinstance(term, str) or not term.strip() or len(term) > 500
                    for term in terms
                ):
                    raise ValueError("Text rubric requires 1–100 nonempty terms, up to 500 characters each")
        return self


class ProblemManifest(DomainModel):
    schema_version: Literal["1.0", "1.1"] = "1.0"
    id: Identifier
    version: Version
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=20_000)
    category: str = Field(min_length=1, max_length=100)
    difficulty: Literal["introductory", "intermediate", "advanced"]
    initial_resources: list[InitialResource] = Field(default_factory=list, max_length=20)
    allowed_ai_capabilities: list[Identifier] = Field(default_factory=lambda: ["chat"], max_length=20)
    allowed_tools: list[Identifier] = Field(default_factory=list, max_length=50)
    ai_policy: AIPolicy = Field(default_factory=AIPolicy)
    tool_permissions: list[Identifier] = Field(default_factory=list, max_length=50)
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    submission: SubmissionSpecification
    evaluation: EvaluationSpecification

    @model_validator(mode="after")
    def unique_resources(self) -> "ProblemManifest":
        names = [resource.name for resource in self.initial_resources]
        if len(names) != len(set(names)):
            raise ValueError("Initial resource names must be unique")
        return self


class ProblemPackageError(ValueError):
    """Invalid or unsupported package structure (with no file contents in errors)."""


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ProblemPackageError("Duplicate JSON object key")
        result[key] = value
    return result


def load_problem_package(directory: str | Path) -> ProblemManifest:
    """Read only a bounded regular manifest.json through a directory file descriptor.

    The operator selects a local directory. Symlink package roots/manifests are
    refused; no archive extraction, resource paths, imports, or executable hooks.
    """
    path = Path(directory)
    try:
        directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open("manifest.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
            with os.fdopen(fd, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_MANIFEST_BYTES:
                    raise ProblemPackageError("Manifest must be a regular file of at most 1 MiB")
                data = stream.read(MAX_MANIFEST_BYTES + 1)
                if len(data) > MAX_MANIFEST_BYTES:
                    raise ProblemPackageError("Manifest exceeds 1 MiB")
        finally:
            os.close(directory_fd)
        parsed = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ProblemPackageError("Cannot read a valid UTF-8 manifest.json from this package") from exc
    return ProblemManifest.model_validate(parsed)


def manifest_digest(manifest: ProblemManifest) -> str:
    data = manifest.model_dump(mode="json")
    if manifest.schema_version == "1.0":
        # M1 registry immutability relies on its historical canonical representation.
        # Added defaults do not change an unchanged manifest's identity. Non-default
        # policy additions still affect the hash, so schema1.0 cannot hide changes.
        if manifest.ai_policy == AIPolicy():
            data.pop("ai_policy")
        if not manifest.tool_permissions:
            data.pop("tool_permissions")
        original_limits = {"max_messages", "max_message_chars", "max_submission_chars"}
        defaults = ResourceLimits().model_dump(mode="json")
        data["resource_limits"] = {
            key: value for key, value in data["resource_limits"].items()
            if key in original_limits or value != defaults[key]
        }
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def public_problem(manifest: ProblemManifest) -> dict:
    """Explicit allowlist: private evaluator configuration never crosses this boundary."""
    return {
        "id": manifest.id, "version": manifest.version, "title": manifest.title,
        "description": manifest.description, "category": manifest.category,
        "difficulty": manifest.difficulty,
        "initial_resources": [resource.model_dump(mode="json") for resource in manifest.initial_resources],
        "allowed_ai_capabilities": list(manifest.allowed_ai_capabilities),
        "allowed_tools": list(manifest.allowed_tools),
        "ai_policy": manifest.ai_policy.model_dump(mode="json"),
        "tool_permissions": list(manifest.tool_permissions),
        "resource_limits": manifest.resource_limits.model_dump(mode="json"),
        "submission": manifest.submission.model_dump(mode="json"),
        "evaluation": {
            "evaluator_id": manifest.evaluation.evaluator_id,
            "evaluator_version": manifest.evaluation.evaluator_version,
            "criteria": [
                {"id": item.id, "title": item.title, "description": item.description, "max_score": item.max_score}
                for item in manifest.evaluation.criteria
            ],
        },
    }
