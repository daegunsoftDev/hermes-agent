"""Host-owned context is separate from model-controlled request data."""

from types import MappingProxyType
import unittest
import pytest
from hermes_cli.model_call_policy import _policy_payload

REQUEST = {"model": "synthetic-model", "messages": []}


def owned(**changes):
    values = {
        "profile": "routed-profile",
        "workspace": "/synthetic/project",
        "conversation_key": "synthetic:shared-thread",
        "boundary_epoch": 7,
    }
    values.update(changes)
    return MappingProxyType(values)


class ModelPolicyContextTest(unittest.TestCase):
    def test_owned_profile_wins_over_process_metadata(self):
        payload = _policy_payload(
            REQUEST, profile="process-default", runtime_context=owned()
        )
        self.assertEqual(payload["profile"], "routed-profile")


def test_legacy_call_without_context_preserves_its_payload():
    payload = _policy_payload(
        REQUEST, profile="process-default", task_id="task-fixture"
    )
    assert payload["profile"] == "process-default"
    assert payload["task_id"] == "task-fixture"
    assert not {"workspace", "conversation_key", "boundary_epoch"}.intersection(payload)


def test_model_request_cannot_assert_host_context():
    request = {**REQUEST, "runtime_context": dict(owned()), "metadata": dict(owned())}
    payload = _policy_payload(request, profile="process-default")
    assert payload["profile"] == "process-default"
    assert "conversation_key" not in payload


@pytest.mark.parametrize("epoch", [0, 7, None])
def test_context_fields_and_explicit_unknowns_survive(epoch):
    scope = owned(workspace=None, boundary_epoch=epoch)
    payload = _policy_payload(REQUEST, profile="process-default", runtime_context=scope)
    assert {key: payload.get(key) for key in scope} == dict(scope)


@pytest.mark.parametrize("epoch", [True, False, -1, "7", 7.0])
def test_context_epoch_rejects_bool_coercion_and_negative_values(epoch):
    with pytest.raises((TypeError, ValueError)):
        _policy_payload(REQUEST, runtime_context=owned(boundary_epoch=epoch))


def test_characterization_registered_kwargs_guard_preserves_legacy_and_context(
    monkeypatch,
):
    from hermes_cli import plugins
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
    from hermes_cli.model_call_policy import enforce_pre_model_call_policy

    manager = PluginManager()
    manager._discovered = True
    monkeypatch.setattr(plugins, "get_plugin_manager", lambda: manager)
    context = PluginContext(PluginManifest(name="context-fixture"), manager)
    seen = []

    def guard(*, profile, **fields):
        seen.append(
            (profile, fields.get("conversation_key"), fields.get("boundary_epoch"))
        )
        return {"action": "allow"}

    context.register_hook("pre_model_call_policy", guard)
    enforce_pre_model_call_policy(REQUEST, profile="process-default")
    enforce_pre_model_call_policy(
        REQUEST, profile="process-default", runtime_context=owned()
    )
    assert seen == [
        ("process-default", None, None),
        ("routed-profile", "synthetic:shared-thread", 7),
    ]
