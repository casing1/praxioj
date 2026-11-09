"""Provider-neutral values. Endpoint credentials never belong to these models."""

from typing import Literal, Protocol, runtime_checkable

from pydantic import Field, JsonValue, model_validator

from praxioj.core import DomainModel, Identifier


class ProviderCapabilities(DomainModel):
    tools: bool = False
    system_messages: bool = True
    temperature: bool = True
    token_limit_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"


class ToolCall(DomainModel):
    id: Identifier
    name: Identifier
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class Message(DomainModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str = Field(default="", max_length=1_048_576)
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=32)
    tool_call_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_role(self) -> "Message":
        if self.role == "tool" and len(self.content.encode("utf-8")) > 1_048_576:
            raise ValueError("Tool message content exceeds its byte size limit")
        if self.role != "tool" and len(self.content) > 100_000:
            raise ValueError("Non-tool message content exceeds its size limit")
        if not self.content and not (self.role == "assistant" and self.tool_calls):
            raise ValueError("A message requires content or assistant tool calls")
        if self.tool_calls and self.role != "assistant":
            raise ValueError("Only assistant messages may request tools")
        if (self.role == "tool") != (self.tool_call_id is not None):
            raise ValueError("Tool messages require a tool call ID exclusively")
        return self


class ModelConfig(DomainModel):
    provider: Identifier = "mock"
    model: str = Field(default="praxioj-mock-v1", min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:@+-]*$")
    temperature: float | None = Field(default=0, ge=0, le=2)
    max_output_tokens: int = Field(default=512, ge=1, le=32768)


class Usage(DomainModel):
    input_tokens: int | None = Field(default=None, ge=0, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, strict=True)
    estimated: bool = False


class ToolResult(DomainModel):
    call_id: Identifier
    status: Literal["completed", "failed", "unsupported", "denied"]
    content: JsonValue


class RuntimeContext(DomainModel):
    session_id: str | None = None
    allowed_capabilities: list[str] = Field(default_factory=lambda: ["chat"])
    allowed_tools: list[str] = Field(default_factory=list)
    tool_definitions: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=50)


class ProviderResponse(DomainModel):
    content: str = Field(default="", max_length=20_000)
    model: str = Field(min_length=1, max_length=256)
    usage: Usage
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=32)
    provider_request_id: str | None = Field(default=None, max_length=256)
    finish_reason: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def nonempty_response(self) -> "ProviderResponse":
        if not self.content and not self.tool_calls:
            raise ValueError("Provider response requires content or tool calls")
        if len({call.id for call in self.tool_calls}) != len(self.tool_calls):
            raise ValueError("Provider returned duplicate tool call IDs")
        return self


class ProviderError(RuntimeError):
    """Safe error metadata only; adapters must never pass upstream error messages."""

    def __init__(self, message: str = "AI provider failed", *, code: str = "provider_error", retryable: bool = False, http_status: int | None = None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.http_status = http_status


class ProviderTimeout(ProviderError):
    def __init__(self):
        super().__init__("AI provider request timed out", code="provider_timeout", retryable=True)


class UsageLimitExceeded(ProviderError):
    pass


@runtime_checkable
class AIProvider(Protocol):
    provider_id: str
    capabilities: ProviderCapabilities

    async def generate(self, messages: list[Message], config: ModelConfig, context: RuntimeContext) -> ProviderResponse: ...


def validate_request(messages: list[Message], config: ModelConfig, context: RuntimeContext, capabilities: ProviderCapabilities) -> None:
    """Validate role boundaries and complete tool correlations before network I/O."""
    if not messages or messages[-1].role not in {"user", "tool"}:
        raise ProviderError("A conversation must end in a user or tool message", code="invalid_conversation")
    if "chat" not in context.allowed_capabilities:
        raise ProviderError("Chat is not allowed by this problem", code="capability_denied")
    if config.temperature is not None and not capabilities.temperature:
        raise ProviderError("This provider does not support temperature", code="unsupported_capability")
    if context.tool_definitions and (not capabilities.tools or "tool_calling" not in context.allowed_capabilities):
        raise ProviderError("Tool calling is not supported or permitted", code="unsupported_capability")
    pending: set[str] = set()
    seen_conversation = False
    for message in messages:
        if message.role == "system":
            if seen_conversation or not capabilities.system_messages:
                raise ProviderError("System messages are not supported in this position", code="invalid_conversation")
        else:
            seen_conversation = True
        if message.role == "tool":
            if not capabilities.tools or message.tool_call_id not in pending:
                raise ProviderError("Invalid tool message correlation", code="invalid_conversation")
            pending.remove(message.tool_call_id)
        else:
            if pending:
                raise ProviderError("Missing tool results", code="invalid_conversation")
            if message.tool_calls and (not capabilities.tools or "tool_calling" not in context.allowed_capabilities):
                raise ProviderError("Tool calling is not supported or permitted", code="unsupported_capability")
            for call in message.tool_calls:
                if call.id in pending:
                    raise ProviderError("Duplicate tool call ID", code="invalid_conversation")
                pending.add(call.id)
    if pending:
        raise ProviderError("Missing tool results", code="invalid_conversation")
