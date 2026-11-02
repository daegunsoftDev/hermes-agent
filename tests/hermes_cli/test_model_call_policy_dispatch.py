"""Real plugin callback failures must not become model-policy permission."""

import threading
import pytest
from hermes_cli import plugins
from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
from hermes_cli.model_call_policy import resolve_pre_model_call_policy


@pytest.fixture
def policy_context(monkeypatch):
    manager = PluginManager()
    manager._discovered = True
    monkeypatch.setattr(plugins, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(plugins, "_resolve_hook_callback_timeout", lambda: 0.02)
    return PluginContext(PluginManifest(name="policy-fixture"), manager)


def test_a_raising_model_guard_denies_instead_of_disappearing(policy_context):
    def broken(**kwargs):
        raise RuntimeError("synthetic guard failure")

    policy_context.register_hook("pre_model_call_policy", broken)
    assert resolve_pre_model_call_policy(session_id="fixture")["action"] == "deny"


def test_a_timed_out_model_guard_cannot_later_allow_the_request(policy_context):
    released = threading.Event()

    def late_allow(**kwargs):
        released.wait(timeout=0.25)
        return {"action": "allow"}

    policy_context.register_hook("pre_model_call_policy", late_allow)
    try:
        decision = resolve_pre_model_call_policy(session_id="fixture")
    finally:
        released.set()
    assert decision["action"] == "deny"


def test_ordinary_observer_errors_still_fail_open(policy_context):
    def broken(**kwargs):
        raise RuntimeError("ordinary observer failure")

    policy_context.register_hook("pre_api_request", broken)
    assert policy_context._manager.invoke_hook("pre_api_request") == []
