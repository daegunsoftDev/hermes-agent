"""Native provider adapters for the shared, opt-in model-policy engine."""

from __future__ import annotations
import contextvars
import threading
from contextlib import contextmanager
from functools import wraps
from typing import Any
from hermes_cli import lifecycle
from hermes_cli.model_call_policy import (
    ModelCallPolicyDenied,
    ModelCallPolicyHalt,
    enforce_pre_model_call_policy,
)


def find_policy_halt(error):
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if not isinstance(current, BaseException) or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, ModelCallPolicyHalt):
            return current
        if isinstance(current, ModelCallPolicyDenied):
            return ModelCallPolicyHalt(current.action, current.message)
        pending.extend((current.__cause__, current.__context__))
    return None


def policy_failure_result(error, messages, api_calls):
    halt = find_policy_halt(error)
    if halt is None:
        return None
    return {
        "completed": False,
        "failed": True,
        "error": "SESSION_POLICY_REJECTED",
        "failure_reason": "session_policy_rejected",
        "failure_retryable": False,
        "policy_action": halt.action,
        "final_response": halt.message,
        "messages": messages,
        "api_calls": api_calls,
    }


@contextmanager
def _attempt(request, metadata):
    if metadata is not None:
        enforce_pre_model_call_policy(request, **metadata)
    try:
        yield
    except Exception as error:
        if (halt := find_policy_halt(error)) is not None:
            raise halt from error
        raise


def _legacy_metadata():
    from hermes_cli.profiles import current_profile_name
    from agent.kanban_turn_recovery import kanban_task_id

    return {
        "profile": current_profile_name(default="default"),
        "task_id": kanban_task_id() or "",
    }


def _main_metadata(agent, request):
    if not lifecycle.has_hook("pre_model_call_policy"):
        return None
    return {
        "call_kind": "conversation",
        **_legacy_metadata(),
        "model": request.get("model") or getattr(agent, "model", ""),
        "provider": getattr(agent, "provider", ""),
        "api_mode": getattr(agent, "api_mode", ""),
        "base_url": getattr(agent, "base_url", ""),
        "session_id": getattr(agent, "session_id", ""),
        "platform": getattr(agent, "platform", ""),
        "is_subagent": getattr(agent, "is_subagent", False),
    }


def main_call(callback):
    @wraps(callback)
    def guarded(agent, request, *args, **kwargs):
        with _attempt(request, _main_metadata(agent, request)):
            return callback(agent, request, *args, **kwargs)

    return guarded


def main_method(callback):
    @wraps(callback)
    def guarded(owner, request, *args, **kwargs):
        with _attempt(request, _main_metadata(owner.agent, request)):
            return callback(owner, request, *args, **kwargs)

    return guarded


def main_request(agent):
    def decorate(callback):
        @wraps(callback)
        def guarded(request, *args, **kwargs):
            with _attempt(request, _main_metadata(agent, request)):
                return callback(request, *args, **kwargs)

        return guarded

    return decorate


def _aux_metadata(client, request, kwargs):
    if not lifecycle.has_hook("pre_model_call_policy"):
        return None
    from agent.auxiliary_client import _RELAY_AUX_CALL_CONTEXT

    context = _RELAY_AUX_CALL_CONTEXT.get() or {}
    return {
        "call_kind": "auxiliary",
        **_legacy_metadata(),
        "auxiliary_task": str(context.get("task") or ""),
        "provider": kwargs.get("provider") or context.get("provider") or "",
        "model": request.get("model") or "",
        "base_url": str(getattr(client, "base_url", "")),
        "api_mode": kwargs.get("api_mode")
        or context.get("api_mode")
        or "chat_completions",
    }


def auxiliary_call(callback):
    @wraps(callback)
    def guarded(client, request, *args, **kwargs):
        with _attempt(request, _aux_metadata(client, request, kwargs)):
            return callback(client, request, *args, **kwargs)

    return guarded


def auxiliary_async_call(callback):
    @wraps(callback)
    async def guarded(client, request, *args, **kwargs):
        with _attempt(request, _aux_metadata(client, request, kwargs)):
            return await callback(client, request, *args, **kwargs)

    return guarded


def _context_thread_target(callback):
    """Bind a no-argument thread target to the caller's ContextVars."""
    context = contextvars.copy_context()
    return lambda: context.run(callback)


def _relay_stream_identity(agent, name_default: str) -> dict:
    """``session_id``/``name``/``model_name`` kwargs for ``relay_llm.stream``."""
    return {
        "session_id": str(getattr(agent, "session_id", "") or ""),
        "name": str(getattr(agent, "provider", "") or name_default),
        "model_name": str(getattr(agent, "model", "") or ""),
    }


def _release_sync_semaphore_after_stream(
    stream: Any, semaphore: threading.BoundedSemaphore
):
    """Release a permit only after a streaming response is consumed or closed."""
    try:
        yield from stream
    finally:
        try:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        finally:
            semaphore.release()
