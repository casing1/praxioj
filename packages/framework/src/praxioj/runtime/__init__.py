"""Provider-neutral AI runtime with offline mock and OpenAI-compatible adapters."""

import math

from praxioj.runtime.models import (
    AIProvider, Message, ModelConfig, ProviderCapabilities, ProviderError,
    ProviderResponse, ProviderTimeout, RuntimeContext, ToolCall, ToolResult,
    Usage, UsageLimitExceeded, validate_request,
)
from praxioj.runtime.compatible import OpenAICompatibleProvider


class MockProvider:
    provider_id = "mock"
    capabilities = ProviderCapabilities(tools=True)
    DEFAULT_RESPONSES = (
        "Start by defining a clear goal. Then describe how you will verify the result and identify a risk with a mitigation. This is a predefined mock response; I have not executed or inspected anything.",
        "Review your draft against each published criterion. Make the goal, verification steps, and risk explicit, then submit your own final plan. This is a predefined mock response.",
    )

    def __init__(self, responses: tuple[str, ...] | list[str] | None = None):
        self.responses = tuple(self.DEFAULT_RESPONSES if responses is None else responses)
        if not self.responses or any(not item or len(item) > 20_000 for item in self.responses):
            raise ValueError("Mock responses must contain nonempty bounded text")

    async def generate(self, messages: list[Message], config: ModelConfig, context: RuntimeContext) -> ProviderResponse:
        if config.provider != self.provider_id or config.model != "praxioj-mock-v1":
            raise ProviderError("Unsupported mock provider or model")
        validate_request(messages, config, context, self.capabilities)
        turn = sum(message.role == "user" for message in messages)
        calls = []
        if messages[-1].role == "tool":
            response = "The workspace tool returned a result. Review plan.txt and the tool status before submitting your final plan."
        elif ("save a release plan" in messages[-1].content.casefold()
              and "workspace.write_file" in context.allowed_tools and context.tool_definitions):
            response = ""
            calls = [ToolCall(id=f"mock-write-{turn}", name="write_file", arguments={
                "path": "plan.txt", "content": "Goal: ship a focused release.\nVerification: run regression tests and review results.\nRisk: regressions; mitigate with a rollback plan.\n",
            })]
        else:
            response = self.responses[(max(turn, 1) - 1) % len(self.responses)]
        response = response[: config.max_output_tokens * 4]
        output_chars = len(response) + sum(len(call.model_dump_json()) for call in calls)
        return ProviderResponse(
            content=response, model=config.model, tool_calls=calls,
            usage=Usage(input_tokens=sum(math.ceil(len(item.content) / 4) for item in messages),
                        output_tokens=math.ceil(output_chars / 4), estimated=True),
            finish_reason="tool_calls" if calls else "stop",
        )


class AIRuntime:
    def __init__(self, provider: AIProvider):
        self.provider = provider

    async def respond(self, messages: list[Message], config: ModelConfig, max_messages: int,
                      context: RuntimeContext | None = None) -> ProviderResponse:
        if sum(message.role == "user" for message in messages) > max_messages:
            raise UsageLimitExceeded("Session message limit reached", code="message_limit")
        context = context or RuntimeContext()
        # Backward-compatible third-party M1 adapters have no capabilities attribute.
        caps = getattr(self.provider, "capabilities", ProviderCapabilities())
        validate_request(messages, config, context, caps)
        if config.provider != self.provider.provider_id:
            raise ProviderError("Provider does not match model configuration", code="invalid_configuration")
        try:
            response = await self.provider.generate(messages, config, context)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("AI provider failed") from None
        if response.tool_calls and (not caps.tools or "tool_calling" not in context.allowed_capabilities or not context.tool_definitions):
            raise ProviderError("Provider requested tools without permission", code="unexpected_tool_calls")
        return response


__all__ = ["AIProvider", "AIRuntime", "Message", "MockProvider", "ModelConfig", "OpenAICompatibleProvider",
           "ProviderCapabilities", "ProviderError", "ProviderResponse", "ProviderTimeout", "RuntimeContext",
           "ToolCall", "ToolResult", "Usage", "UsageLimitExceeded"]
