import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from praxioj.problems import load_problem_package, manifest_digest
from praxioj.runtime import AIRuntime, Message, MockProvider, ModelConfig, RuntimeContext, ToolCall
from praxioj.tools import (
    InMemoryWorkspaceStore, ToolDispatcher, ToolPolicyContext, WorkspaceLimits,
    default_tool_registry, validate_workspace_path,
)
from praxioj.tracing import EventType, InMemoryTraceCollector, TraceEnvelope

ROOT = Path(__file__).resolve().parents[2]


def test_old_manifest_digest_stays_compatible_and_new_policy_changes_identity():
    manifest = load_problem_package(ROOT / "examples/problems/release-plan")
    assert manifest_digest(manifest) == "0c5425eba5f6b5a79c67d5471d80a341497bce7555c2820f59f7985fc4e2e32c"
    original = manifest_digest(manifest)
    manifest.resource_limits.max_model_calls = 2
    assert manifest_digest(manifest) != original
    manifest.resource_limits.max_model_calls = 30
    manifest.ai_policy.allowed_models = ["local/model:v1"]
    assert manifest_digest(manifest) != original


@pytest.mark.parametrize("path", ["/etc/passwd", "../file", "a/../b", "a/./b", "a//b", "a/", ".", "..", "a\\b", "C:secret", "a\x00b", "%2e%2e/file", "a/%252e%252e", " a", "a?b", "a#b"])
def test_workspace_paths_reject_traversal_and_ambiguous_keys(path):
    with pytest.raises(ValueError):
        validate_workspace_path(path)
    with pytest.raises(ValueError):
        InMemoryWorkspaceStore().write(path, "text")


def policy(**changes):
    return ToolPolicyContext(session_id="one", allowed_tools=["workspace.read_file", "workspace.write_file"],
                             permissions=changes.pop("permissions", ["workspace:read", "workspace:write"]), **changes)


def test_tools_are_strict_permission_checked_and_sessions_are_isolated():
    registry = default_tool_registry()
    dispatcher = ToolDispatcher(registry)
    one, two = InMemoryWorkspaceStore(), InMemoryWorkspaceStore()
    call = ToolCall(id="call1", name="write_file", arguments={"path": "notes/plan.txt", "content": "Goal"})
    denied = dispatcher.execute(call, policy(permissions=[]), one)
    assert denied.result.status == "denied" and denied.result.content["code"] == "permission_denied"
    assert one.list_files() == []
    result = dispatcher.execute(call, policy(), one)
    assert result.result.status == "completed" and result.modified_file.revision == 1
    assert two.read("notes/plan.txt") is None
    read = dispatcher.execute(ToolCall(id="call2", name="read_file", arguments={"path": "notes/plan.txt"}), policy(), one)
    assert read.result.content["content"] == "Goal" and read.modified_file is None
    assert dispatcher.execute(call, policy(), one).modified_file.revision == 2
    definitions = registry.definitions(["workspace.write_file"])
    assert [item["function"]["name"] for item in definitions] == ["write_file"]
    assert definitions[0]["function"]["parameters"]["additionalProperties"] is False
    definitions[0]["function"]["parameters"]["injected"] = True
    assert "injected" not in registry.definitions(["workspace.write_file"])[0]["function"]["parameters"]


@pytest.mark.parametrize("arguments", [
    {"path": "../escape", "content": "x"}, {"path": "x", "content": 12},
    {"path": "x", "content": "text", "session_id": "victim"}, {"path": "x"}, {"path": 3, "content": "x"},
])
def test_tool_input_validation_happens_before_mutation(arguments):
    store = InMemoryWorkspaceStore()
    dispatcher = ToolDispatcher(default_tool_registry())
    outcome = dispatcher.execute(ToolCall(id="bad", name="write_file", arguments=arguments), policy(), store)
    assert outcome.result.status == "denied" and outcome.result.content["code"] == "invalid_tool_input"
    assert store.list_files() == []


def test_unknown_and_unallowed_tools_fail_closed():
    dispatcher = ToolDispatcher(default_tool_registry())
    unknown = ToolCall(id="a", name="shell", arguments={"command": "whoami"})
    assert dispatcher.authorize(unknown, policy()).code == "unknown_tool"
    context = policy()
    context.allowed_tools = []
    call = ToolCall(id="b", name="read_file", arguments={"path": "plan.txt"})
    assert dispatcher.authorize(call, context).code == "tool_not_allowed"


def test_workspace_quotas_measure_utf8_bytes_and_preserve_state_on_failure():
    limits = WorkspaceLimits(max_file_bytes=6, max_workspace_bytes=8, max_workspace_files=2)
    store = InMemoryWorkspaceStore(limits)
    store.write("a", "한글")
    with pytest.raises(ValueError):
        store.write("a", "한글자")
    store.write("b", "12")
    with pytest.raises(ValueError):
        store.write("c", "")
    with pytest.raises(ValueError):
        store.write("b", "123")
    assert [item.content for item in store.list_files()] == ["한글", "12"]
    dispatcher = ToolDispatcher(default_tool_registry())
    outcome = dispatcher.execute(ToolCall(id="c", name="write_file", arguments={"path": "a", "content": "한글자"}), policy(limits=limits), store)
    assert outcome.result.content["code"] == "file_size_limit"
    with pytest.raises(ValidationError):
        store.read("a").content = "mutated"


def test_dispatcher_enforces_policy_quotas_even_if_store_has_more_capacity():
    store = InMemoryWorkspaceStore()
    context = policy(limits=WorkspaceLimits(max_workspace_files=1, max_workspace_bytes=4))
    dispatcher = ToolDispatcher(default_tool_registry())
    call = ToolCall(id="a", name="write_file", arguments={"path": "a", "content": "1234"})
    assert dispatcher.execute(call, context, store).result.status == "completed"
    another = ToolCall(id="b", name="write_file", arguments={"path": "b", "content": "x"})
    assert dispatcher.execute(another, context, store).result.status == "failed"
    assert len(store.list_files()) == 1


def test_mock_tool_roundtrip_preserves_conversation_and_records_real_tool_result():
    registry = default_tool_registry()
    context = RuntimeContext(allowed_capabilities=["chat", "tool_calling"], allowed_tools=["workspace.write_file"],
                             tool_definitions=registry.definitions(["workspace.write_file"]))
    messages = [Message(role="user", content="Please save a release plan")]
    runtime = AIRuntime(MockProvider())
    response = asyncio.run(runtime.respond(messages, ModelConfig(), 2, context))
    assert response.tool_calls[0].name == "write_file"
    store = InMemoryWorkspaceStore()
    result = ToolDispatcher(registry).execute(response.tool_calls[0], policy(), store)
    messages.extend([Message(role="assistant", content=response.content, tool_calls=response.tool_calls),
                     Message(role="tool", tool_call_id=result.result.call_id, content=json.dumps(result.result.model_dump()))])
    final = asyncio.run(runtime.respond(messages, ModelConfig(), 2, context))
    assert not final.tool_calls and "plan.txt" in final.content
    assert store.read("plan.txt").content.startswith("Goal:")
    assert final.usage.estimated is True


def test_trace_correlations_sequence_and_event_identity_are_preserved():
    collector = InMemoryTraceCollector()
    parent = TraceEnvelope(session_id="one", sequence_number=1, event_type=EventType.PROVIDER_CALL_STARTED,
                           correlation_id="run-1", resource_ids={"provider_call_id": "call1"})
    child = TraceEnvelope(session_id="one", sequence_number=2, event_type=EventType.TOOL_CALL_AUTHORIZED,
                          correlation_id="run-1", parent_event_id=str(parent.event_id), resource_ids={"tool_call_id": "tool1"})
    collector.append(parent)
    collector.append(child)
    collector.append(child)
    assert [item.sequence_number for item in collector.read("one")] == [1, 2]
    assert collector.read("one")[1].parent_event_id == str(parent.event_id)
    assert collector.read("two") == []


def test_tool_message_envelope_has_room_without_relaxing_other_role_limits():
    # A legal100k-byte file plus JSON metadata must remain usable as model context.
    assert Message(role="tool", tool_call_id="call-1", content="x" * 100_500).content
    for role in ["user", "system", "assistant"]:
        with pytest.raises(ValidationError):
            Message(role=role, content="x" * 100_001)
    with pytest.raises(ValidationError):
        Message(role="tool", tool_call_id="call-1", content="x" * 1_048_577)
    with pytest.raises(ValidationError):
        Message(role="tool", tool_call_id="call-1", content="가" * 349_526)
