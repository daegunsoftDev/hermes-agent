"""Policy vetoes through current product modules and actual SDK memory transport.

All data is synthetic. No model server, credentials, private metadata or SDK-private
retry overrides are used. SDK retries are explicitly zero, matching the host factories.
"""

from dataclasses import dataclass
from types import SimpleNamespace
import json
import threading
import httpx
import pytest
from openai import OpenAI, AsyncOpenAI
from agent import auxiliary_client as aux
from agent import chat_completion_helpers as main
from agent.chat_completion_nonstream import _NonStreamRequest
from hermes_cli import plugins
from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
from hermes_cli.model_call_policy import ModelCallPolicyHalt, ModelCallPolicyDenied

REQUEST = {"model": "synthetic", "messages": [{"role": "user", "content": "fixture"}]}
RESPONSE = {
    "id": "chatcmpl-fixture",
    "object": "chat.completion",
    "created": 0,
    "model": "synthetic",
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "fixture response"},
        }
    ],
}


@pytest.fixture
def veto(monkeypatch):
    manager = PluginManager()
    manager._discovered = True
    monkeypatch.setattr(plugins, "get_plugin_manager", lambda: manager)
    context = PluginContext(PluginManifest(name="policy-fixture"), manager)
    context.register_hook(
        "pre_model_call_policy",
        lambda **kwargs: {"action": "deny", "message": "fixture veto"},
    )


def _serve(entries):
    def serve(request):
        body = json.loads(request.content)
        entries.append(body)
        if body.get("stream"):
            chunk = {
                "id": "chunk-fixture",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "synthetic",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": "fixture"},
                        "finish_reason": "stop",
                    }
                ],
            }
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=(
                    "data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n"
                ).encode(),
            )
        return httpx.Response(200, json=RESPONSE)

    return serve


@pytest.fixture
def sdk():
    entries = []
    client = OpenAI(
        api_key="fixture",
        base_url="https://model.example/v1",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(_serve(entries))),
    )
    try:
        yield client, entries
    finally:
        client.close()


def _agent(client):
    return SimpleNamespace(
        api_mode="chat_completions",
        provider="openai-api",
        base_url="https://model.example/v1",
        model="synthetic",
        session_id="fixture",
        platform="cli",
        log_prefix="",
        _active_codex_stream_request_token=None,
        _touch_activity=lambda *args: None,
        _client_log_context=lambda: "fixture",
        _create_request_openai_client=lambda **kwargs: client,
        _close_request_openai_client=lambda c, **kwargs: c.close(),
    )


def test_main_dispatch_veto_precedes_sdk_transport(veto, sdk):
    client, entries = sdk
    with pytest.raises(ModelCallPolicyHalt):
        main._dispatch_nonstreaming_api_request(
            _agent(client), dict(REQUEST), make_client=lambda *a, **k: client
        )
    assert entries == []


def test_main_worker_publishes_the_veto_and_unwinds(veto, sdk):
    client, entries = sdk
    request = object.__new__(_NonStreamRequest)
    request.agent, request.api_kwargs = _agent(client), dict(REQUEST)
    request.result = {"response": None, "error": None}
    request.clients = main._RequestClientRegistry(request.agent)
    request.codex_token = request.codex_watchdog_state = None
    request.codex_retired = request.cancelled = False
    worker = threading.Thread(target=main._context_thread_target(request._call))
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert isinstance(request.result["error"], ModelCallPolicyHalt)
    assert request.result["response"] is None
    assert request.clients.client is None
    assert entries == []


def test_main_stream_veto_precedes_opening_sdk_stream(veto, sdk):
    client, entries = sdk
    call = object.__new__(main._StreamingCall)
    call.agent = _agent(client)
    call.clients = main._RequestClientRegistry(call.agent)
    call.last_chunk_time = {"t": 0}
    response = None
    try:
        with pytest.raises(ModelCallPolicyHalt):
            response = call._open_chat_stream({**REQUEST, "stream": True})
    finally:
        if response is not None:
            response.close()
    assert entries == []


@pytest.mark.parametrize("stream", [False, True])
def test_auxiliary_sync_veto_precedes_sdk_transport(veto, sdk, stream):
    client, entries = sdk
    response = None
    try:
        with pytest.raises(ModelCallPolicyHalt):
            response = (
                aux._relay_sync_stream(client, {**REQUEST, "stream": True})
                if stream
                else aux._relay_sync_completion(client, dict(REQUEST))
            )
    finally:
        if stream and response is not None:
            response.close()
    assert entries == []


@pytest.mark.asyncio
async def test_auxiliary_async_veto_precedes_sdk_transport(veto):
    entries = []
    async with AsyncOpenAI(
        api_key="fixture",
        base_url="https://model.example/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_serve(entries))),
    ) as client:
        with pytest.raises(ModelCallPolicyHalt):
            await aux._relay_async_completion(client, dict(REQUEST))
    assert entries == []


@pytest.mark.parametrize("path", ["main", "auxiliary"])
def test_no_policy_keeps_normal_sdk_dispatch(sdk, path):
    client, entries = sdk
    response = (
        main._dispatch_nonstreaming_api_request(
            _agent(client), dict(REQUEST), make_client=lambda *a, **k: client
        )
        if path == "main"
        else aux._relay_sync_completion(client, dict(REQUEST))
    )
    assert response.choices[0].message.content == "fixture response"
    assert len(entries) == 1
    assert entries[0]["model"] == "synthetic"


@dataclass
class _Phase:
    action: str = "fallthrough"
    result: object = None


@pytest.mark.parametrize("wrapped", [False, True])
def test_turn_loop_settles_typed_denial_before_provider_recovery(monkeypatch, wrapped):
    from agent import conversation_loop as loop

    state = SimpleNamespace(
        retry_count=0,
        max_retries=3,
        thinking_spinner=None,
        messages=[],
        api_call_count=1,
    )

    def preparation(agent):
        return _Phase()

    def provider_step(agent):
        if not wrapped:
            raise ModelCallPolicyHalt(action="deny", message="fixture veto")

        def reject(request):
            raise ModelCallPolicyDenied(action="deny", message="fixture veto")

        with OpenAI(
            api_key="fixture",
            base_url="https://model.example/v1",
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(reject)),
        ) as client:
            client.chat.completions.create(**REQUEST)

    def recovery(agent, api_error):
        pytest.fail("policy rejection reached normal provider recovery")

    monkeypatch.setattr(loop, "nous_rate_limit_guard", preparation)
    monkeypatch.setattr(loop, "build_api_request", preparation)
    monkeypatch.setattr(loop, "perform_api_call", provider_step)
    monkeypatch.setattr(loop, "handle_api_error", recovery)
    try:
        result = loop._run_api_retry_loop(SimpleNamespace(), state)
    except ModelCallPolicyHalt:
        pytest.fail("policy rejection escaped the terminal turn boundary")
    assert result["completed"] is False
    assert result["failed"] is True
    assert result["error"] == "SESSION_POLICY_REJECTED"
    assert result["failure_reason"] == "session_policy_rejected"
    assert result["failure_retryable"] is False
    assert state.retry_count == 0
