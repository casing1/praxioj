"""Permission-checked text tools over session-bound logical stores.

No filesystem, shell, code interpreter, HTTP client, or sandbox is exposed here.
A platform store must enforce these same quotas atomically within its session.
"""

import re
from dataclasses import dataclass
from typing import Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator, model_validator

from praxioj.core import DomainModel, Identifier, content_digest
from praxioj.runtime.models import ToolCall, ToolResult

_PATH = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_-][A-Za-z0-9_.-]*)*$")


def validate_workspace_path(path: str) -> str:
    """Validate a portable logical key; never normalize it into a host path."""
    if not isinstance(path, str) or not 1 <= len(path) <= 128 or not _PATH.fullmatch(path):
        raise ValueError("Invalid workspace path")
    if any(part in {".", ".."} for part in path.split("/")):
        raise ValueError("Invalid workspace path")
    return path


class WorkspaceLimits(DomainModel):
    max_file_bytes: int = Field(default=16_384, ge=1, le=100_000)
    max_workspace_bytes: int = Field(default=65_536, ge=1, le=1_048_576)
    max_workspace_files: int = Field(default=8, ge=1, le=100)


class WorkspaceDocument(DomainModel):
    model_config = ConfigDict(frozen=True)
    path: str
    content: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    revision: int = Field(ge=1)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_workspace_path(value)

    @model_validator(mode="after")
    def validate_integrity(self) -> "WorkspaceDocument":
        if self.sha256 != content_digest(self.content) or self.byte_size != len(self.content.encode("utf-8")):
            raise ValueError("Workspace content metadata mismatch")
        return self


class WorkspaceStore(Protocol):
    def read(self, path: str) -> WorkspaceDocument | None: ...
    def write(self, path: str, content: str) -> WorkspaceDocument: ...
    def list_files(self) -> list[WorkspaceDocument]: ...


class InMemoryWorkspaceStore:
    """Single-threaded reference store, explicitly instantiated per session."""

    def __init__(self, limits: WorkspaceLimits | None = None):
        self.limits = (limits or WorkspaceLimits()).model_copy(deep=True)
        self._files: dict[str, WorkspaceDocument] = {}

    def read(self, path: str) -> WorkspaceDocument | None:
        return self._files.get(validate_workspace_path(path))

    def write(self, path: str, content: str) -> WorkspaceDocument:
        path = validate_workspace_path(path)
        if not isinstance(content, str):
            raise ValueError("File content must be text")
        size = len(content.encode("utf-8"))
        prior = self._files.get(path)
        if size > self.limits.max_file_bytes:
            raise ValueError("Workspace file size limit exceeded")
        if len(self._files) + (prior is None) > self.limits.max_workspace_files:
            raise ValueError("Workspace file count limit exceeded")
        if sum(item.byte_size for item in self._files.values()) - (prior.byte_size if prior else 0) + size > self.limits.max_workspace_bytes:
            raise ValueError("Workspace total size limit exceeded")
        item = WorkspaceDocument(path=path, content=content, sha256=content_digest(content), byte_size=size,
                                 revision=(prior.revision + 1) if prior else 1)
        self._files[path] = item
        return item

    def list_files(self) -> list[WorkspaceDocument]:
        return sorted(self._files.values(), key=lambda item: item.path)


class ToolSpec(DomainModel):
    id: Identifier
    name: Identifier
    description: str = Field(min_length=1, max_length=2000)
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue]
    required_permissions: list[str]
    execution_limits: dict[str, JsonValue] = Field(default_factory=dict)


class ToolPolicyContext(DomainModel):
    session_id: str = Field(min_length=1, max_length=128)
    allowed_tools: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    limits: WorkspaceLimits = Field(default_factory=WorkspaceLimits)


class AuthorizationDecision(DomainModel):
    allowed: bool
    code: str
    message: str


class ToolExecutionOutcome(DomainModel):
    result: ToolResult
    modified_file: WorkspaceDocument | None = None


class _ReadInput(DomainModel):
    model_config = ConfigDict(strict=True)
    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_workspace_path(value)


class _WriteInput(_ReadInput):
    content: str = Field(max_length=100_000)


class _FileOutput(DomainModel):
    model_config = ConfigDict(strict=True)
    path: str
    content: str
    sha256: str
    byte_size: int
    revision: int


@dataclass(frozen=True)
class _RegisteredTool:
    spec: ToolSpec
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel, WorkspaceStore], WorkspaceDocument]
    modifies_artifact: bool


class ToolRegistry:
    def __init__(self):
        self._by_name: dict[str, _RegisteredTool] = {}
        self._ids: set[str] = set()

    def register(self, spec: ToolSpec, input_model: type[BaseModel], output_model: type[BaseModel],
                 handler: Callable[[BaseModel, WorkspaceStore], WorkspaceDocument], *, modifies_artifact: bool = False) -> None:
        """Trusted application code registers handlers, never problem manifests."""
        if spec.name in self._by_name or spec.id in self._ids:
            raise ValueError("Duplicate tool registration")
        self._by_name[spec.name] = _RegisteredTool(spec.model_copy(deep=True), input_model, output_model, handler, modifies_artifact)
        self._ids.add(spec.id)

    def definitions(self, allowed_tools: list[str]) -> list[dict]:
        return [{"type": "function", "function": {"name": entry.spec.name, "description": entry.spec.description,
                                                  "parameters": entry.spec.model_dump(mode="json")["input_schema"]}}
                for entry in self._by_name.values() if entry.spec.id in allowed_tools]

    def specs(self) -> list[ToolSpec]:
        return [entry.spec.model_copy(deep=True) for entry in self._by_name.values()]


class ToolDispatcher:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def authorize(self, call: ToolCall, context: ToolPolicyContext) -> AuthorizationDecision:
        entry = self.registry._by_name.get(call.name)
        if entry is None:
            return AuthorizationDecision(allowed=False, code="unknown_tool", message="This tool is unavailable")
        if entry.spec.id not in context.allowed_tools:
            return AuthorizationDecision(allowed=False, code="tool_not_allowed", message="This tool is not allowed by the problem")
        if not set(entry.spec.required_permissions).issubset(context.permissions):
            return AuthorizationDecision(allowed=False, code="permission_denied", message="Required tool permission is missing")
        try:
            value = entry.input_model.model_validate(call.arguments, strict=True)
            if isinstance(value, _WriteInput) and len(value.content.encode("utf-8")) > context.limits.max_file_bytes:
                return AuthorizationDecision(allowed=False, code="file_size_limit", message="Workspace file size limit exceeded")
        except (ValidationError, ValueError, UnicodeError):
            return AuthorizationDecision(allowed=False, code="invalid_tool_input", message="Tool input does not satisfy its schema")
        return AuthorizationDecision(allowed=True, code="allowed", message="Tool request authorized")

    def execute(self, call: ToolCall, context: ToolPolicyContext, store: WorkspaceStore) -> ToolExecutionOutcome:
        decision = self.authorize(call, context)
        if not decision.allowed:
            return ToolExecutionOutcome(result=ToolResult(call_id=call.id, status="denied", content=decision.model_dump(mode="json")))
        entry = self.registry._by_name[call.name]
        try:
            value = entry.input_model.model_validate(call.arguments, strict=True)
            if isinstance(value, _WriteInput):
                files = store.list_files()
                existing = next((item for item in files if item.path == value.path), None)
                if len(files) + (existing is None) > context.limits.max_workspace_files:
                    raise ValueError("Workspace file count limit exceeded")
                if sum(item.byte_size for item in files) - (existing.byte_size if existing else 0) + len(value.content.encode("utf-8")) > context.limits.max_workspace_bytes:
                    raise ValueError("Workspace total size limit exceeded")
            document = entry.handler(value, store)
            output = entry.output_model.model_validate(document.model_dump(), strict=True)
            return ToolExecutionOutcome(result=ToolResult(call_id=call.id, status="completed", content=output.model_dump(mode="json")),
                                        modified_file=document if entry.modifies_artifact else None)
        except FileNotFoundError:
            result = {"code": "file_not_found", "message": "Workspace file does not exist"}
        except Exception:
            # Storage and handlers may contain private diagnostics; never echo them.
            result = {"code": "tool_execution_failed", "message": "Tool execution failed or a workspace limit was reached"}
        return ToolExecutionOutcome(result=ToolResult(call_id=call.id, status="failed", content=result))


def _read_file(value: _ReadInput, store: WorkspaceStore) -> WorkspaceDocument:
    document = store.read(value.path)
    if document is None:
        raise FileNotFoundError
    return document


def _write_file(value: _WriteInput, store: WorkspaceStore) -> WorkspaceDocument:
    return store.write(value.path, value.content)


def default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool_id, name, description, input_model, handler, permission, modifies in [
        ("workspace.read_file", "read_file", "Read one UTF-8 text file in this session's logical workspace.", _ReadInput, _read_file, "workspace:read", False),
        ("workspace.write_file", "write_file", "Create or replace one bounded UTF-8 text file in this session's logical workspace.", _WriteInput, _write_file, "workspace:write", True),
    ]:
        registry.register(ToolSpec(id=tool_id, name=name, description=description,
                                  input_schema=input_model.model_json_schema(), output_schema=_FileOutput.model_json_schema(),
                                  required_permissions=[permission], execution_limits={"scope": "session", "bounded_by": "WorkspaceLimits", "network": False}),
                          input_model, _FileOutput, handler, modifies_artifact=modifies)
    return registry


__all__ = ["ToolSpec", "ToolRegistry", "ToolDispatcher", "ToolPolicyContext", "AuthorizationDecision", "WorkspaceDocument",
           "WorkspaceStore", "InMemoryWorkspaceStore", "WorkspaceLimits", "ToolExecutionOutcome", "default_tool_registry", "validate_workspace_path"]
