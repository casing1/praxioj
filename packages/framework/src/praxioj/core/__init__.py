"""Shared value types only; no dependency on other framework modules."""

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def content_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")]
Version = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")]


class Artifact(DomainModel):
    """An inline snapshot, never a host path or an instruction to execute."""

    model_config = ConfigDict(frozen=True)

    id: Identifier
    name: str = Field(min_length=1, max_length=128, pattern=r"^[^/\\]+$")
    content: str = Field(max_length=100_000)
    media_type: str = "text/plain"
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_digest(self) -> "Artifact":
        if content_digest(self.content) != self.sha256:
            raise ValueError("Artifact digest does not match its content")
        return self
