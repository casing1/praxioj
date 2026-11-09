"""Durable records around a single-process, asynchronous AI/tool execution loop.

Every provider await happens outside database transactions. No implicit retry:
remote providers may have charged even when their response was not received.
"""
import asyncio
from hashlib import sha256
import json
import logging
from time import monotonic

from fastapi import HTTPException
from sqlalchemy import select

from praxioj.runtime import (AIRuntime, Message, MockProvider, ModelConfig,
    OpenAICompatibleProvider, ProviderCapabilities, ProviderError, RuntimeContext, ToolCall)
from praxioj.tools import ToolDispatcher, ToolPolicyContext, WorkspaceLimits, default_tool_registry
from praxioj.tracing import EventType, redact_payload
from .models import ConversationMessage, ProviderCall, SolveSession, WorkspaceRun, utcnow
from .services import append_trace, manifest_for, messages_for
from .workspace import DatabaseWorkspaceStore

logger = logging.getLogger("praxioj.internal.runtime")
TERMINAL = {"completed", "failed", "cancelled"}
PROVIDER_CODES = {"provider_error", "provider_timeout", "provider_connection_error", "provider_http_error",
                  "invalid_configuration", "invalid_provider_response", "context_limit", "response_limit",
                  "unexpected_tool_calls", "capability_denied", "invalid_conversation", "unsupported_capability", "message_limit"}
ERROR_MESSAGES = {
    "provider_timeout": "The provider request timed out; usage may be incomplete.",
    "run_timeout": "The run exceeded its time limit.",
    "cancelled": "The run was cancelled; provider usage may be incomplete.",
    "interrupted": "The server restarted before this run finished. Start a new run to continue.",
    "model_call_limit": "This session's model call limit has been reached.",
    "tool_call_limit": "This session's tool call limit has been reached.",
    "token_limit": "This session's observed token limit has been reached.",
    "usage_unknown": "A prior call has unknown usage; the token budget prevents another call.",
    "duplicate_tool_call": "The provider returned a repeated tool call identifier.",
    "provider_unavailable": "The selected provider profile is not configured.",
}


def safe_error(code):
    return {"code": code, "message": ERROR_MESSAGES.get(code, "The AI runtime could not complete this run.")}


def scrub(value, settings):
    """Best effort free-text redaction plus exact configured-secret protection."""
    def exact(item):
        if isinstance(item, str):
            return item.replace(settings.llm_api_key, "[REDACTED]") if settings.llm_api_key else item
        if isinstance(item, list):
            return [exact(v) for v in item]
        if isinstance(item, dict):
            return {k: exact(v) for k, v in item.items()}
        return item
    return redact_payload({"value": exact(value)})["value"]


def workspace_limits(manifest):
    limits = manifest.resource_limits
    return WorkspaceLimits(max_file_bytes=limits.max_file_bytes, max_workspace_bytes=limits.max_workspace_bytes,
                           max_workspace_files=limits.max_workspace_files)


def profiles(settings):
    result = {"mock": {"id": "mock", "label": "Offline Mock", "model": "praxioj-mock-v1",
                       "capabilities": MockProvider().capabilities.model_dump(mode="json")}}
    if settings.llm_base_url and settings.llm_model:
        result["compatible"] = {"id": "compatible", "label": "OpenAI-compatible", "model": settings.llm_model,
                                "capabilities": ProviderCapabilities(tools=settings.llm_supports_tools,
                                    system_messages=settings.llm_supports_system,
                                    temperature=settings.llm_supports_temperature,
                                    token_limit_parameter=settings.llm_token_parameter).model_dump(mode="json")}
    return result


def configure_session(settings, manifest, requested):
    profile_id = requested or settings.default_profile
    profile = profiles(settings).get(profile_id)
    if profile is None:
        raise HTTPException(422, "Runtime profile is not configured")
    policy = manifest.ai_policy
    if policy.allowed_providers and profile_id not in policy.allowed_providers:
        raise HTTPException(403, "Provider is not allowed by this problem")
    if policy.allowed_models and profile["model"] not in policy.allowed_models:
        raise HTTPException(403, "Model is not allowed by this problem")
    if manifest.allowed_tools and (not profile["capabilities"]["tools"] or "tool_calling" not in manifest.allowed_ai_capabilities):
        raise HTTPException(403, "Problem tools require a provider with tool calling support")
    model = ModelConfig(provider=profile_id, model=profile["model"],
        temperature=0 if policy.allow_temperature and profile["capabilities"]["temperature"] else None,
        max_output_tokens=min(512, policy.max_output_tokens))
    snapshot = {"capabilities": profile["capabilities"], "pricing": {}}
    if profile_id == "compatible":
        snapshot["pricing"] = {"input_per_million": settings.price_input_per_million,
                               "output_per_million": settings.price_output_per_million,
                               "currency": settings.price_currency}
    return profile_id, model.model_dump(mode="json"), snapshot


def usage_for(db, session, manifest):
    calls = list(db.scalars(select(ProviderCall).where(ProviderCall.session_id == session.id)))
    runs = list(db.scalars(select(WorkspaceRun).where(WorkspaceRun.session_id == session.id)))
    complete = all(c.input_tokens is not None and c.output_tokens is not None for c in calls)
    incoming = sum(c.input_tokens or 0 for c in calls)
    outgoing = sum(c.output_tokens or 0 for c in calls)
    prices = session.profile_snapshot.get("pricing", {})
    pin, pout = prices.get("input_per_million"), prices.get("output_per_million")
    configured = pin is not None or pout is not None
    cost = ((incoming * (pin or 0) + outgoing * (pout or 0)) / 1_000_000) if configured else None
    return {"model_calls": len(calls), "tool_calls": sum(len(r.tool_calls) for r in runs),
            "input_tokens": incoming, "output_tokens": outgoing, "usage_complete": complete,
            "estimated": any(c.estimated for c in calls), "cost_estimate": cost,
            "currency": prices.get("currency") if configured else None,
            "cost_estimate_complete": configured and complete and pin is not None and pout is not None,
            "limits": manifest.resource_limits.model_dump(mode="json")}


def budget_code(usage, limits):
    if usage["model_calls"] >= limits.max_model_calls:
        return "model_call_limit"
    if limits.max_total_tokens is not None:
        if not usage["usage_complete"]:
            return "usage_unknown"
        if usage["input_tokens"] + usage["output_tokens"] >= limits.max_total_tokens:
            return "token_limit"
    return None


class RunManager:
    def __init__(self, app):
        self.app = app
        self.tasks = {}
        self.registry = default_tool_registry()
        self.dispatcher = ToolDispatcher(self.registry)

    def launch(self, run_id):
        if run_id not in self.tasks:
            task = asyncio.create_task(self.execute(run_id))
            self.tasks[run_id] = task
            task.add_done_callback(lambda finished: self._finished(run_id, finished))

    def _finished(self, run_id, task):
        self.tasks.pop(run_id, None)
        if not task.cancelled() and task.exception() is not None:
            # Retrieving the exception prevents asyncio from emitting raw SQL or
            # upstream content if recovery persistence itself encountered an outage.
            logger.error("runtime_failure code=state_persistence_failed run_id=%s", run_id)

    def cancel(self, run_id):
        task = self.tasks.get(run_id)
        if task:
            task.cancel()

    async def shutdown(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def recover(self):
        with self.app.state.session_factory() as db:
            ids = list(db.scalars(select(WorkspaceRun.id).where(WorkspaceRun.status.in_(["queued", "running"]))))
        for run_id in ids:
            self.finish(run_id, "failed", "interrupted")

    def _locked(self, db, run_id):
        # Always session then run: the same lock order as participant endpoints.
        run = db.get(WorkspaceRun, run_id)
        if run is None:
            return None, None
        session = db.scalar(select(SolveSession).where(SolveSession.id == run.session_id).with_for_update())
        db.refresh(run)
        return session, run

    def finish(self, run_id, status, code=None, provider_details=None):
        provider_details = provider_details or {}
        with self.app.state.session_factory.begin() as db:
            session, run = self._locked(db, run_id)
            if run is None or run.status in TERMINAL:
                return
            for call in db.scalars(select(ProviderCall).where(ProviderCall.run_id == run.id, ProviderCall.status == "started")):
                call.status, call.error_code, call.finished_at = "failed", code, utcnow()
                append_trace(db, session, EventType.PROVIDER_CALL_COMPLETED,
                    {"status": "failed", "code": code, "usage": {"input_tokens": None, "output_tokens": None}, **provider_details},
                    resource_ids={"run_id": run.id, "provider_call_id": call.id}, correlation_id=run.id)
            # A stopped tool loop must not leave unmatched tool requests in history.
            history = messages_for(db, session.id)
            pending = {}
            for message in history:
                if message.role == "assistant":
                    for tool in message.tool_calls:
                        pending[tool["id"]] = tool
                elif message.role == "tool":
                    pending.pop(message.tool_call_id, None)
            next_position = len(history) + 1
            for tool in pending.values():
                refs = {"run_id": run.id, "tool_call_id": tool["id"]}
                requested = append_trace(db, session, EventType.TOOL_CALL_REQUESTED,
                    {"name": tool["name"], "arguments": tool["arguments"]}, actor="assistant",
                    resource_ids=refs, correlation_id=run.id)
                authorized = append_trace(db, session, EventType.TOOL_CALL_AUTHORIZED,
                    {"allowed": False, "code": code or status,
                     "message": "The run stopped before this tool could execute."},
                    resource_ids=refs, correlation_id=run.id, parent_event_id=str(requested.event_id))
                result = {"call_id": tool["id"], "status": "denied",
                          "content": {"code": code or status, "executed": False}}
                append_trace(db, session, EventType.TOOL_CALL_COMPLETED, result,
                    resource_ids=refs, correlation_id=run.id, parent_event_id=str(authorized.event_id))
                db.add(ConversationMessage(session_id=session.id, position=next_position,
                    role="tool", tool_call_id=tool["id"], content=json.dumps(result)))
                next_position += 1
            run.status, run.error, run.finished_at = status, safe_error(code) if code else None, utcnow()
            session.active_run_id = None
            if code:
                append_trace(db, session, EventType.ERROR, {"stage": "ai_runtime", **safe_error(code)},
                             resource_ids={"run_id": run.id}, correlation_id=run.id)
            append_trace(db, session, EventType.SESSION_STATE_CHANGED,
                         {"run_status": status, "session_status": session.status},
                         resource_ids={"run_id": run.id}, correlation_id=run.id)
        if code:
            logger.warning("runtime_failure code=%s run_id=%s http_status=%s", code, run_id, provider_details.get("http_status"))

    async def execute(self, run_id):
        try:
            with self.app.state.session_factory.begin() as db:
                session, run = self._locked(db, run_id)
                if run is None or run.status in TERMINAL:
                    return
                if run.cancel_requested:
                    raise asyncio.CancelledError()
                _, manifest = manifest_for(db, session)
                seconds = manifest.resource_limits.max_run_seconds
                run.status = "running"
                append_trace(db, session, EventType.SESSION_STATE_CHANGED, {"run_status": "running"},
                             resource_ids={"run_id": run.id}, correlation_id=run.id)
            deadline = monotonic() + seconds
            async with asyncio.timeout(seconds):
                await self.loop(run_id, deadline)
                check_deadline(deadline)
            self.finish(run_id, "completed")
        except asyncio.CancelledError:
            self.finish(run_id, "cancelled", "cancelled")
        except TimeoutError:
            self.finish(run_id, "failed", "run_timeout")
        except ProviderError as exc:
            # The adapter exposes only controlled codes. Never log exception text.
            code = exc.code if exc.code in PROVIDER_CODES else "provider_error"
            status = exc.http_status if type(exc.http_status) is int and 100 <= exc.http_status <= 599 else None
            self.finish(run_id, "failed", code, {"http_status": status, "retryable": exc.retryable is True})
        except RunFailure as exc:
            self.finish(run_id, "failed", exc.code)
        except Exception:
            self.finish(run_id, "failed", "runtime_failed")

    async def loop(self, run_id, deadline):
        while True:
            check_deadline(deadline)
            with self.app.state.session_factory.begin() as db:
                session, run = self._locked(db, run_id)
                if run.cancel_requested:
                    raise asyncio.CancelledError()
                _, manifest = manifest_for(db, session)
                limits = manifest.resource_limits
                code = budget_code(usage_for(db, session, manifest), limits)
                if code:
                    raise RunFailure(code)
                model = ModelConfig.model_validate(session.model_configuration)
                history = [Message(role=m.role, content=m.content, tool_calls=m.tool_calls,
                                   tool_call_id=m.tool_call_id) for m in messages_for(db, session.id)]
                context = RuntimeContext(session_id=session.id, allowed_capabilities=manifest.allowed_ai_capabilities,
                    allowed_tools=manifest.allowed_tools, tool_definitions=self.registry.definitions(manifest.allowed_tools))
                capabilities = session.profile_snapshot.get("capabilities", {})
                profile = session.runtime_profile
                call = ProviderCall(session_id=session.id, run_id=run.id)
                db.add(call)
                db.flush()
                call_id = call.id
                started = append_trace(db, session, EventType.PROVIDER_CALL_STARTED,
                    {"provider": model.provider, "model": model.model, "status": "started"},
                    resource_ids={"run_id": run.id, "provider_call_id": call_id}, correlation_id=run.id)
                started_id = str(started.event_id)
            # No transaction, lock, or database connection spans the network await.
            settings = self.app.state.settings
            if profile == "mock":
                runtime = self.app.state.runtime
            else:
                if not settings.llm_base_url:
                    raise RunFailure("provider_unavailable")
                runtime = AIRuntime(OpenAICompatibleProvider(settings.llm_base_url, api_key=settings.llm_api_key,
                    capabilities=ProviderCapabilities.model_validate(capabilities),
                    timeout_seconds=min(settings.llm_timeout_seconds, limits.request_timeout_seconds)))
            try:
                async with asyncio.timeout(limits.request_timeout_seconds):
                    reply = await runtime.respond(history, model, limits.max_messages, context)
            except TimeoutError:
                raise RunFailure("provider_timeout") from None
            payload = scrub(reply.model_dump(mode="json"), settings)
            with self.app.state.session_factory.begin() as db:
                session, run = self._locked(db, run_id)
                call = db.get(ProviderCall, call_id)
                call.status, call.finished_at = "completed", utcnow()
                call.input_tokens, call.output_tokens = reply.usage.input_tokens, reply.usage.output_tokens
                call.estimated, call.provider_request_id = reply.usage.estimated, payload.get("provider_request_id")
                event = append_trace(db, session, EventType.PROVIDER_CALL_COMPLETED,
                    {"status": "completed", "model": payload["model"], "usage": reply.usage.model_dump(mode="json"),
                     "provider_request_id": call.provider_request_id, "finish_reason": payload.get("finish_reason")},
                    resource_ids={"run_id": run.id, "provider_call_id": call.id}, correlation_id=run.id,
                    parent_event_id=started_id)
                completed_id = str(event.event_id)
            with self.app.state.session_factory.begin() as db:
                session, run = self._locked(db, run_id)
                if run.cancel_requested:
                    raise asyncio.CancelledError()
                tools = payload["tool_calls"]
                ids = [t["id"] for t in tools]
                if len(set(ids)) != len(ids) or any(i in run.tool_calls for i in ids):
                    raise RunFailure("duplicate_tool_call")
                message = ConversationMessage(session_id=session.id, position=len(messages_for(db, session.id)) + 1,
                    role="assistant", content=payload["content"], tool_calls=tools)
                db.add(message)
                db.flush()
                append_trace(db, session, EventType.ASSISTANT_MESSAGE,
                    {"content": message.content, "tool_calls": tools}, actor="assistant",
                    resource_ids={"run_id": run.id, "provider_call_id": call.id, "message_id": message.id},
                    correlation_id=run.id, parent_event_id=completed_id)
            if not tools:
                return
            for item in tools:
                await asyncio.sleep(0)
                check_deadline(deadline)
                with self.app.state.session_factory.begin() as db:
                    session, run = self._locked(db, run_id)
                    if run.cancel_requested:
                        raise asyncio.CancelledError()
                    if usage_for(db, session, manifest)["tool_calls"] >= limits.max_tool_calls:
                        raise RunFailure("tool_call_limit")
                    call = ToolCall.model_validate(item)
                    run.tool_calls = [*run.tool_calls, call.id]
                    refs = {"run_id": run.id, "provider_call_id": call_id, "tool_call_id": call.id}
                    requested = append_trace(db, session, EventType.TOOL_CALL_REQUESTED,
                        {"name": call.name, "arguments": call.arguments}, actor="assistant",
                        resource_ids=refs, correlation_id=run.id)
                    policy = ToolPolicyContext(session_id=session.id, allowed_tools=manifest.allowed_tools,
                        permissions=manifest.tool_permissions, limits=workspace_limits(manifest))
                    decision = self.dispatcher.authorize(call, policy)
                    authorized = append_trace(db, session, EventType.TOOL_CALL_AUTHORIZED,
                        decision.model_dump(mode="json"), resource_ids=refs, correlation_id=run.id,
                        parent_event_id=str(requested.event_id))
                    outcome = self.dispatcher.execute(call, policy,
                        DatabaseWorkspaceStore(db, session.id, workspace_limits(manifest)))
                    result = scrub(outcome.result.model_dump(mode="json"), settings)
                    append_trace(db, session, EventType.TOOL_CALL_COMPLETED, result, resource_ids=refs,
                        correlation_id=run.id, parent_event_id=str(authorized.event_id))
                    if outcome.modified_file:
                        document = outcome.modified_file
                        append_trace(db, session, EventType.ARTIFACT_UPDATED,
                            {"path": document.path, "sha256": document.sha256, "byte_size": document.byte_size,
                             "revision": document.revision}, resource_ids=refs, correlation_id=run.id)
                    db.add(ConversationMessage(session_id=session.id, position=len(messages_for(db, session.id)) + 1,
                        role="tool", tool_call_id=call.id, content=json.dumps(result, ensure_ascii=False)))
            # Yield even for a deterministic mock loop, enabling reads/cancellation.
            await asyncio.sleep(0)


class RunFailure(Exception):
    def __init__(self, code):
        self.code = code


def check_deadline(deadline):
    # Synchronous DB/tool transactions cannot be preempted. This guard prevents
    # starting another call/mutation after the elapsed wall-clock budget.
    if monotonic() >= deadline:
        raise RunFailure("run_timeout")
