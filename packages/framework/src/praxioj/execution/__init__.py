"""Execution contracts only. Milestone 1 does not provide a security sandbox."""

from typing import Literal, Protocol

from pydantic import Field

from praxioj.core import Artifact, DomainModel


class ExecutionLimits(DomainModel):
    cpu_seconds: int = Field(default=30, ge=1, le=3600)
    memory_mb: int = Field(default=256, ge=16, le=16384)
    disk_mb: int = Field(default=64, ge=1, le=4096)
    network_policy: Literal["deny", "allowlist"] = "deny"
    allowed_hosts: list[str] = Field(default_factory=list)


class Workspace(DomainModel):
    id: str
    session_id: str
    backend: str
    metadata: dict[str, str] = Field(default_factory=dict)


class ToolExecutionRequest(DomainModel):
    tool_name: str
    arguments: dict[str, str] = Field(default_factory=dict)


class ToolExecutionResult(DomainModel):
    status: Literal["completed", "failed", "unsupported"]
    output: str
    artifacts: list[Artifact] = Field(default_factory=list)


class ExecutionBackend(Protocol):
    def create(self, session_id: str, limits: ExecutionLimits) -> Workspace: ...
    def read_file(self, workspace: Workspace, relative_path: str) -> bytes: ...
    def write_file(self, workspace: Workspace, relative_path: str, content: bytes) -> None: ...
    def execute_tool(self, workspace: Workspace, request: ToolExecutionRequest) -> ToolExecutionResult: ...
    def collect_artifacts(self, workspace: Workspace) -> list[Artifact]: ...
    def cleanup(self, workspace: Workspace) -> None: ...


class UnavailableExecutionBackend:
    """Fails closed instead of passing paths or commands to the host."""

    def create(self, session_id: str, limits: ExecutionLimits) -> Workspace:
        raise NotImplementedError("Workspace execution is not implemented in Milestone 1")

    def read_file(self, workspace: Workspace, relative_path: str) -> bytes:
        raise NotImplementedError("Workspace file access is not implemented in Milestone 1")

    def write_file(self, workspace: Workspace, relative_path: str, content: bytes) -> None:
        raise NotImplementedError("Workspace file access is not implemented in Milestone 1")

    def execute_tool(self, workspace: Workspace, request: ToolExecutionRequest) -> ToolExecutionResult:
        raise NotImplementedError("Tool execution is not implemented in Milestone 1")

    def collect_artifacts(self, workspace: Workspace) -> list[Artifact]:
        raise NotImplementedError("Workspace artifacts are not implemented in Milestone 1")

    def cleanup(self, workspace: Workspace) -> None:
        raise NotImplementedError("Workspace lifecycle is not implemented in Milestone 1")
