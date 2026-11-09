"""Bounded, non-streaming Chat Completions adapter for configured compatible APIs.

The network is used only by this server-configured provider, never by an AI tool.
Responses are read incrementally to enforce a byte bound, not exposed as SSE.
"""

import asyncio
import ipaddress
import json
from urllib.parse import urlsplit

import httpx
from pydantic import JsonValue, SecretStr

from praxioj.runtime.models import (
    Message, ModelConfig, ProviderCapabilities, ProviderError, ProviderResponse,
    ProviderTimeout, RuntimeContext, ToolCall, Usage, validate_request,
)
from praxioj.tracing import redact_payload

MAX_REQUEST_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 1_048_576


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate object key")
        result[key] = value
    return result


def _json_loads(value: str | bytes):
    return json.loads(value, object_pairs_hook=_unique_keys, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


class OpenAICompatibleProvider:
    provider_id = "compatible"

    def __init__(self, base_url: str, api_key: str | None = None,
                 capabilities: ProviderCapabilities | None = None, timeout_seconds: float = 30,
                 transport: httpx.AsyncBaseTransport | None = None):
        try:
            url = urlsplit(base_url)
            if (url.scheme not in {"http", "https"} or not url.hostname or url.username is not None
                    or url.password is not None or url.query or url.fragment or "?" in base_url or "#" in base_url
                    or any(char.isspace() or ord(char) < 32 for char in base_url) or "\\" in base_url or "%" in url.netloc):
                raise ValueError
            _ = url.port
            if url.scheme == "http":
                local = url.hostname in {"localhost", "host.docker.internal"}
                try:
                    address = ipaddress.ip_address(url.hostname)
                    # Private address literals support explicitly configured LAN LLMs.
                    local_ranges = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
                    local = local or address.is_loopback or any(address in ipaddress.ip_network(network) for network in local_ranges)
                except ValueError:
                    pass
                if not local:
                    raise ValueError
            if not 0 < timeout_seconds <= 120:
                raise ValueError
            if api_key is not None and (len(api_key) > 4096 or any(ord(char) < 33 or ord(char) > 126 for char in api_key)):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("Invalid server-side provider endpoint or configuration") from None
        self._endpoint = base_url.rstrip("/") + "/chat/completions"
        self._api_key = SecretStr(api_key) if api_key else None
        self.capabilities = (capabilities or ProviderCapabilities()).model_copy(deep=True)
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    def _sanitize(self, value: JsonValue) -> JsonValue:
        key = self._api_key.get_secret_value() if self._api_key else None

        def replace(item: JsonValue) -> JsonValue:
            if isinstance(item, str):
                return item.replace(key, "[REDACTED]") if key else item
            if isinstance(item, dict):
                return {str(replace(name)): replace(data) for name, data in item.items()}
            if isinstance(item, list):
                return [replace(data) for data in item]
            return item
        return redact_payload({"value": replace(value)})["value"]

    async def generate(self, messages: list[Message], config: ModelConfig, context: RuntimeContext) -> ProviderResponse:
        if config.provider != self.provider_id:
            raise ProviderError("Provider does not match model configuration", code="invalid_configuration")
        validate_request(messages, config, context, self.capabilities)
        wire_messages = []
        for message in messages:
            wire = {"role": message.role, "content": message.content}
            if message.tool_calls:
                wire["tool_calls"] = [{"id": call.id, "type": "function", "function": {
                    "name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False, allow_nan=False),
                }} for call in message.tool_calls]
            if message.tool_call_id:
                wire["tool_call_id"] = message.tool_call_id
            wire_messages.append(wire)
        payload = {"model": config.model, "messages": wire_messages, "stream": False,
                   self.capabilities.token_limit_parameter: config.max_output_tokens}
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        if context.tool_definitions:
            payload["tools"] = context.tool_definitions
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(raw) > MAX_REQUEST_BYTES or len(messages) > 500:
            raise ProviderError("Provider context exceeds the request size limit", code="context_limit")
        headers = {"Content-Type": "application/json", "Accept": "application/json", "Accept-Encoding": "identity"}
        if self._api_key:
            headers["Authorization"] = "Bearer " + self._api_key.get_secret_value()
        try:
            # A deadline bounds the entire operation, including slow trickling bodies.
            async with asyncio.timeout(self.timeout_seconds):
                async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False,
                                             follow_redirects=False, transport=self._transport) as client:
                    async with client.stream("POST", self._endpoint, content=raw, headers=headers) as response:
                        if response.status_code != 200:
                            status = response.status_code
                            raise ProviderError("AI provider rejected the request", code="provider_http_error",
                                                retryable=status in {408, 429} or status >= 500, http_status=status)
                        if response.headers.get("Content-Encoding", "identity").lower() not in {"", "identity"}:
                            raise ProviderError("Compressed provider responses are unsupported", code="invalid_provider_response")
                        data = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=16_384):
                            data.extend(chunk)
                            if len(data) > MAX_RESPONSE_BYTES:
                                raise ProviderError("Provider response exceeds the size limit", code="response_limit")
            return self._parse_response(bytes(data), config, context)
        except (TimeoutError, httpx.TimeoutException):
            raise ProviderTimeout() from None
        except httpx.RequestError:
            raise ProviderError("Cannot connect to AI provider", code="provider_connection_error", retryable=True) from None
        except ProviderError:
            raise
        except (ValueError, TypeError, KeyError, IndexError, RecursionError, UnicodeError):
            raise ProviderError("AI provider returned an invalid response", code="invalid_provider_response") from None

    def _parse_response(self, data: bytes, config: ModelConfig, context: RuntimeContext) -> ProviderResponse:
        body = _json_loads(data)
        if not isinstance(body, dict) or not isinstance(body.get("choices"), list) or len(body["choices"]) != 1:
            raise ValueError("Expected one completion")
        choice = body["choices"][0]
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise ValueError("Expected completion message object")
        message = choice["message"]
        if message.get("role") != "assistant":
            raise ValueError("Expected assistant role")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("Expected text content")
        calls = []
        raw_calls = message.get("tool_calls", [])
        if not isinstance(raw_calls, list) or len(raw_calls) > 32:
            raise ValueError("Invalid tool calls")
        for call in raw_calls:
            if not isinstance(call, dict) or call.get("type") != "function" or not isinstance(call.get("function"), dict):
                raise ValueError("Unsupported tool call type")
            args = _json_loads(call["function"]["arguments"])
            if not isinstance(args, dict):
                raise ValueError("Expected object arguments")
            calls.append(ToolCall(id=self._sanitize(call["id"]), name=self._sanitize(call["function"]["name"]),
                                  arguments=self._sanitize(args)))
        if calls and (not self.capabilities.tools or "tool_calling" not in context.allowed_capabilities or not context.tool_definitions):
            raise ProviderError("Provider requested tools without permission", code="unexpected_tool_calls")
        usage = body.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise ValueError("Invalid usage")
        usage = usage or {}
        return ProviderResponse(
            content=self._sanitize(content or ""), model=self._sanitize(body.get("model", config.model)),
            usage=Usage(input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens")),
            tool_calls=calls, provider_request_id=self._sanitize(body.get("id")),
            finish_reason=self._sanitize(choice.get("finish_reason")),
        )
