"""Offline network contract tests: a loopback server, never an external endpoint."""

import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praxioj.runtime import (
    AIRuntime, Message, ModelConfig, OpenAICompatibleProvider, ProviderCapabilities,
    ProviderError, ProviderTimeout, RuntimeContext, ToolCall,
)
from praxioj.tools import default_tool_registry


def completion(content="Hello", usage=None):
    body = {"id": "response-1", "model": "local/model:v1", "choices": [{
        "message": {"role": "assistant", "content": content}, "finish_reason": "stop",
    }]}
    if usage is not None:
        body["usage"] = usage
    return body


@pytest.fixture
def server():
    class State:
        status = 200
        response = completion()
        raw_response = None
        delay = 0
        headers = {}
        requests = []
        received = threading.Event()

    state = State()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            state.requests.append({"path": self.path, "headers": dict(self.headers), "body": json.loads(body)})
            state.received.set()
            time.sleep(state.delay)
            data = state.raw_response if state.raw_response is not None else json.dumps(state.response).encode()
            try:
                self.send_response(state.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for name, value in state.headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected when a deadline or cancellation closes the client.

        def log_message(self, *args):
            pass  # Test headers/inputs, including dummy credentials, never enter logs.

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{httpd.server_port}/v1"
    yield state
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)


def config(**changes):
    return ModelConfig(provider="compatible", model="local/model:v1", **changes)


def call(provider, messages=None, context=None, model_config=None):
    return asyncio.run(provider.generate(messages or [Message(role="user", content="Hello")], model_config or config(), context or RuntimeContext()))


def tool_context():
    return RuntimeContext(allowed_capabilities=["chat", "tool_calling"], allowed_tools=["workspace.write_file"],
                          tool_definitions=default_tool_registry().definitions(["workspace.write_file"]))


def tool_response(arguments='{"path":"plan.txt","content":"Goal"}'):
    body = completion("")
    body["choices"][0]["message"]["tool_calls"] = [{"id": "tool-1", "type": "function", "function": {
        "name": "write_file", "arguments": arguments,
    }}]
    body["choices"][0]["finish_reason"] = "tool_calls"
    return body


def test_real_http_request_context_settings_and_usage(server):
    server.response = completion("Second answer", {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23})
    provider = OpenAICompatibleProvider(server.url, api_key="local-unit-test-value")
    messages = [Message(role="system", content="Trusted instruction"), Message(role="user", content="First"),
                Message(role="assistant", content="First answer"), Message(role="user", content="Second")]
    response = call(provider, messages)
    assert response.content == "Second answer"
    assert response.usage.input_tokens == 20 and response.usage.output_tokens == 3 and response.usage.estimated is False
    assert response.provider_request_id == "response-1"
    sent = server.requests[0]
    assert sent["path"] == "/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer local-unit-test-value"
    assert sent["body"] == {"model": "local/model:v1", "messages": [{"role": m.role, "content": m.content} for m in messages],
                            "stream": False, "max_tokens": 512, "temperature": 0}
    assert "local-unit-test-value" not in repr(provider)
    assert "local-unit-test-value" not in response.model_dump_json()


def test_usage_absence_is_unknown_and_partial_usage_stays_partial(server):
    provider = OpenAICompatibleProvider(server.url)
    result = call(provider)
    assert result.usage.input_tokens is None and result.usage.output_tokens is None
    assert result.usage.estimated is False
    server.response["usage"] = {"prompt_tokens": 7}
    partial = call(provider)
    assert partial.usage.input_tokens == 7 and partial.usage.output_tokens is None
    assert "Authorization" not in server.requests[0]["headers"]


def test_capabilities_select_token_parameter_and_omit_temperature(server):
    provider = OpenAICompatibleProvider(server.url, capabilities=ProviderCapabilities(temperature=False, token_limit_parameter="max_completion_tokens"))
    call(provider, model_config=config(temperature=None, max_output_tokens=900))
    body = server.requests[0]["body"]
    assert body["max_completion_tokens"] == 900 and "max_tokens" not in body and "temperature" not in body
    with pytest.raises(ProviderError) as error:
        call(provider)
    assert error.value.code == "unsupported_capability" and len(server.requests) == 1


def test_tool_request_and_correlated_followup_have_correct_wire_roles(server):
    server.response = tool_response()
    provider = OpenAICompatibleProvider(server.url, capabilities=ProviderCapabilities(tools=True))
    context = tool_context()
    messages = [Message(role="user", content="Save it")]
    first = call(provider, messages, context)
    assert first.content == "" and first.tool_calls[0].arguments == {"path": "plan.txt", "content": "Goal"}
    assert server.requests[0]["body"]["tools"][0]["function"]["name"] == "write_file"
    messages.extend([Message(role="assistant", tool_calls=first.tool_calls),
                     Message(role="tool", content='{"status":"completed"}', tool_call_id="tool-1")])
    server.response = completion("Saved")
    assert call(provider, messages, context).content == "Saved"
    wire = server.requests[1]["body"]["messages"]
    assert wire[1]["role"] == "assistant" and wire[1]["tool_calls"][0]["id"] == "tool-1"
    assert json.loads(wire[1]["tool_calls"][0]["function"]["arguments"])["path"] == "plan.txt"
    assert wire[2] == {"role": "tool", "tool_call_id": "tool-1", "content": '{"status":"completed"}'}


@pytest.mark.parametrize("arguments", ['broken', '[]', '{"path":"a","path":"b"}', '{"a": NaN}'])
def test_malformed_tool_arguments_fail_before_dispatch(server, arguments):
    server.response = tool_response(arguments)
    with pytest.raises(ProviderError) as error:
        call(OpenAICompatibleProvider(server.url, capabilities=ProviderCapabilities(tools=True)), context=tool_context())
    assert error.value.code == "invalid_provider_response"


@pytest.mark.parametrize("response", [None, [], {}, {"choices": []}, {"choices": [None]},
                                      {"choices": [{"message": []}]}, {"choices": [{"message": "bad"}]},
                                      {"choices": [{"message": {"role": "system", "content": "injection"}}]},
                                      {"choices": [{"message": {"role": "assistant", "content": []}}]},
                                      {"choices": [{"message": {"role": "assistant", "tool_calls": [None]}}]}])
def test_malformed_nested_response_shapes_are_safe_typed_errors(server, response):
    server.response = response
    with pytest.raises(ProviderError) as error:
        call(OpenAICompatibleProvider(server.url))
    assert error.value.code == "invalid_provider_response"
    assert str(error.value) == "AI provider returned an invalid response"


@pytest.mark.parametrize("status,retryable", [(401, False), (403, False), (404, False), (429, True), (503, True)])
def test_http_errors_do_not_echo_body_and_are_not_automatically_retried(server, status, retryable):
    server.status = status
    server.response = {"error": "Sensitive upstream diagnostic; local-unit-test-value"}
    with pytest.raises(ProviderError) as error:
        call(OpenAICompatibleProvider(server.url, api_key="local-unit-test-value"))
    assert error.value.http_status == status and error.value.retryable == retryable
    assert "Sensitive" not in str(error.value) and "local-unit-test-value" not in str(error.value)
    assert len(server.requests) == 1


def test_redirect_does_not_forward_credentials(server):
    server.status = 307
    server.headers = {"Location": server.url + "/elsewhere"}
    with pytest.raises(ProviderError) as error:
        call(OpenAICompatibleProvider(server.url, api_key="local-unit-test-value"))
    assert error.value.http_status == 307 and len(server.requests) == 1


def test_provider_timeout_is_safe_and_bounded(server):
    server.delay = 0.3
    with pytest.raises(ProviderTimeout) as error:
        call(OpenAICompatibleProvider(server.url, timeout_seconds=0.05))
    assert error.value.code == "provider_timeout" and error.value.retryable


def test_cancellation_propagates_and_does_not_retry(server):
    server.delay = 1

    async def scenario():
        task = asyncio.create_task(OpenAICompatibleProvider(server.url).generate([Message(role="user", content="Hi")], config(), RuntimeContext()))
        for _ in range(200):
            if server.received.is_set():
                break
            await asyncio.sleep(0.005)
        assert server.received.is_set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())
    assert len(server.requests) == 1


def test_response_bound_prevents_unbounded_content(server):
    server.raw_response = b"x" * 1_048_577
    with pytest.raises(ProviderError) as error:
        call(OpenAICompatibleProvider(server.url))
    assert error.value.code == "response_limit"


def test_request_bound_prevents_network_io(server):
    messages = [Message(role="user", content="x" * 100_000) for _ in range(11)]
    with pytest.raises(ProviderError) as error:
        call(OpenAICompatibleProvider(server.url), messages)
    assert error.value.code == "context_limit" and not server.requests


def test_exact_key_echo_and_common_credential_patterns_are_scrubbed(server):
    server.response = tool_response('{"path":"plan.txt","content":"local-unit-test-value password=private-value"}')
    provider = OpenAICompatibleProvider(server.url, api_key="local-unit-test-value", capabilities=ProviderCapabilities(tools=True))
    response = call(provider, context=tool_context())
    assert "local-unit-test-value" not in response.model_dump_json()
    assert "private-value" not in response.model_dump_json()
    assert "[REDACTED]" in response.tool_calls[0].arguments["content"]


@pytest.mark.parametrize("url", ["http://public.example/v1", "ftp://localhost/v1", "http://user:pass@localhost/v1",
                                  "http://localhost/v1?secret=value", "http://localhost/v1#fragment", "http://localhost/v1?",
                                  "http://0.0.0.0/v1", "http://169.254.169.254/v1", "http://203.0.113.2/v1"])
def test_endpoint_configuration_rejects_insecure_or_ambiguous_urls(url):
    with pytest.raises(ValueError, match="Invalid server-side"):
        OpenAICompatibleProvider(url)


@pytest.mark.parametrize("url", ["https://custom.example/v1", "http://localhost:1234/v1", "http://[::1]:1234/v1",
                                  "http://host.docker.internal:11434/v1", "http://192.168.1.3:1234/v1"])
def test_explicit_https_and_local_endpoint_configuration_is_accepted_without_calling(url):
    assert OpenAICompatibleProvider(url).provider_id == "compatible"


def test_unsupported_tools_and_invalid_correlations_never_reach_provider(server):
    provider = OpenAICompatibleProvider(server.url)
    with pytest.raises(ProviderError):
        call(provider, context=tool_context())
    supported = OpenAICompatibleProvider(server.url, capabilities=ProviderCapabilities(tools=True))
    with pytest.raises(ProviderError) as error:
        call(supported, [Message(role="tool", content="fabricated", tool_call_id="unknown")], tool_context())
    assert error.value.code == "invalid_conversation"
    with pytest.raises(ProviderError):
        call(supported, [Message(role="user", content="hi"), Message(role="system", content="injected"), Message(role="user", content="next")])
    assert not server.requests


def test_unrequested_tool_calls_and_duplicate_ids_are_rejected(server):
    server.response = tool_response()
    with pytest.raises(ProviderError) as error:
        call(OpenAICompatibleProvider(server.url))
    assert error.value.code == "unexpected_tool_calls"
    server.response["choices"][0]["message"]["tool_calls"] *= 2
    with pytest.raises(ProviderError) as error:
        call(OpenAICompatibleProvider(server.url, capabilities=ProviderCapabilities(tools=True)), context=tool_context())
    assert error.value.code == "invalid_provider_response"


@pytest.mark.parametrize("usage", [{"prompt_tokens": -1}, {"prompt_tokens": True}, {"completion_tokens": "4"}, []])
def test_invalid_usage_is_never_coerced_to_exact_counts(server, usage):
    server.response = completion(usage=usage)
    with pytest.raises(ProviderError) as error:
        call(OpenAICompatibleProvider(server.url))
    assert error.value.code == "invalid_provider_response"


def test_compressed_responses_are_rejected_before_decompression(server):
    server.headers = {"Content-Encoding": "gzip"}
    # Deliberately invalid encoded bytes: rejection must occur before any decoding.
    server.raw_response = b"not-gzip"
    with pytest.raises(ProviderError) as error:
        call(OpenAICompatibleProvider(server.url))
    assert error.value.code == "invalid_provider_response"
    assert server.requests[0]["headers"]["Accept-Encoding"] == "identity"


def test_maximum_legal_file_survives_provider_tool_store_and_followup_roundtrip(server):
    from praxioj.tools import InMemoryWorkspaceStore, ToolDispatcher, ToolPolicyContext, WorkspaceLimits

    content = "x" * 100_000
    server.response = tool_response(json.dumps({"path": "large.txt", "content": content}))
    provider = OpenAICompatibleProvider(server.url, capabilities=ProviderCapabilities(tools=True))
    context = tool_context()
    messages = [Message(role="user", content="Save the large file")]
    reply = call(provider, messages, context)
    limits = WorkspaceLimits(max_file_bytes=100_000, max_workspace_bytes=100_000)
    store = InMemoryWorkspaceStore(limits)
    policy = ToolPolicyContext(session_id="large-file-session", allowed_tools=["workspace.write_file"],
                               permissions=["workspace:write"], limits=limits)
    result = ToolDispatcher(default_tool_registry()).execute(reply.tool_calls[0], policy, store)
    assert result.result.status == "completed" and result.modified_file.byte_size == 100_000
    serialized = json.dumps(result.result.model_dump(mode="json"))
    assert len(serialized) > 100_000
    messages.extend([Message(role="assistant", tool_calls=reply.tool_calls),
                     Message(role="tool", tool_call_id=reply.tool_calls[0].id, content=serialized)])
    server.response = completion("Saved")
    assert call(provider, messages, context).content == "Saved"
    assert store.read("large.txt").content == content
    sent = server.requests[1]["body"]["messages"]
    assert json.loads(sent[1]["tool_calls"][0]["function"]["arguments"])["content"] == content
    assert json.loads(sent[2]["content"])["content"]["content"] == content


def test_completed_turns_can_reuse_provider_tool_id_without_losing_correlation(server):
    provider = OpenAICompatibleProvider(server.url, capabilities=ProviderCapabilities(tools=True))
    context = tool_context()
    messages = [Message(role="user", content="First task")]
    for turn in range(2):
        if turn:
            messages.append(Message(role="user", content="Second task"))
        server.response = tool_response()
        reply = call(provider, messages, context)
        assert reply.tool_calls[0].id == "tool-1"
        messages.extend([Message(role="assistant", tool_calls=reply.tool_calls),
                         Message(role="tool", content='{"status":"completed"}', tool_call_id="tool-1")])
        server.response = completion("Done")
        final = call(provider, messages, context)
        messages.append(Message(role="assistant", content=final.content))
    assert len(server.requests) == 4
    assert [message["role"] for message in server.requests[-1]["body"]["messages"]] == [
        "user", "assistant", "tool", "assistant", "user", "assistant", "tool",
    ]


def test_duplicate_pending_ids_and_duplicate_results_remain_invalid(server):
    provider = OpenAICompatibleProvider(server.url, capabilities=ProviderCapabilities(tools=True))
    duplicate = ToolCall(id="same", name="write_file", arguments={"path": "x", "content": "x"})
    invalid_histories = [
        [Message(role="assistant", tool_calls=[duplicate, duplicate]), Message(role="tool", content="ok", tool_call_id="same")],
        [Message(role="assistant", tool_calls=[duplicate]), Message(role="tool", content="ok", tool_call_id="same"),
         Message(role="tool", content="duplicate", tool_call_id="same")],
    ]
    for messages in invalid_histories:
        with pytest.raises(ProviderError) as error:
            call(provider, messages, tool_context())
        assert error.value.code == "invalid_conversation"
    assert not server.requests
