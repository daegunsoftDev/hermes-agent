# Adapted from NousResearch/hermes-agent PR #97168, source commit
# e33c124e9e76cfb7c1fc57c2e4d7eb33d1a27c76; tool-only helper not adopted.
"""Behavioral contracts for the fail-closed model-call policy."""

import pytest

from hermes_cli.model_call_policy import (
    PRE_MODEL_CALL_POLICY_FAILURE_MESSAGE,
    resolve_pre_model_call_policy,
)
from hermes_cli.plugins import PluginManager


def test_no_listener_allows(monkeypatch):
    monkeypatch.setattr("hermes_cli.lifecycle.has_hook", lambda _name: False)

    assert resolve_pre_model_call_policy(session_id="s1") == {
        "action": "allow",
        "message": "",
    }


def test_none_is_no_opinion(monkeypatch):
    monkeypatch.setattr("hermes_cli.lifecycle.has_hook", lambda _name: True)
    monkeypatch.setattr(
        "hermes_cli.lifecycle.invoke_hook",
        lambda _name, **_payload: [None, {"action": "allow"}],
    )

    assert resolve_pre_model_call_policy(session_id="s1") == {
        "action": "allow",
        "message": "",
    }


@pytest.mark.parametrize(
    "results",
    [
        [
            {"action": "pause", "message": "wait"},
            {"action": "allow"},
            {"action": "deny", "message": "budget exhausted"},
        ],
        [
            {"action": "deny", "message": "budget exhausted"},
            {"action": "allow"},
            {"action": "pause", "message": "wait"},
        ],
    ],
)
def test_deny_wins_independent_of_registration_order(monkeypatch, results):
    monkeypatch.setattr("hermes_cli.lifecycle.has_hook", lambda _name: True)
    monkeypatch.setattr(
        "hermes_cli.lifecycle.invoke_hook",
        lambda _name, **_payload: results,
    )

    assert resolve_pre_model_call_policy(session_id="s1") == {
        "action": "deny",
        "message": "budget exhausted",
    }


@pytest.mark.parametrize(
    "results",
    [
        [{"action": "allow", "message": object()}],
        [{"action": "allow", "unknown": True}],
        [
            {"action": "deny", "message": "valid first"},
            {"action": "allow", "message": object()},
        ],
        [
            {"action": "pause", "message": "valid first"},
            {"action": "allow", "message": object()},
        ],
        [
            {"action": "allow", "message": object()},
            {"action": "deny", "message": "valid second"},
        ],
    ],
)
def test_every_non_none_result_is_validated_before_precedence(monkeypatch, results):
    monkeypatch.setattr("hermes_cli.lifecycle.has_hook", lambda _name: True)
    monkeypatch.setattr(
        "hermes_cli.lifecycle.invoke_hook",
        lambda _name, **_payload: results,
    )

    assert resolve_pre_model_call_policy(session_id="s1") == {
        "action": "deny",
        "message": PRE_MODEL_CALL_POLICY_FAILURE_MESSAGE,
    }
