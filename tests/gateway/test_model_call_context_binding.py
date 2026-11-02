"""Real turn/metadata owners with admitted synthetic routing and DB collaborators.

Policy admission is fixed by the fixture, not live platform authentication.
The shared agent stands for already-resolved/cached reuse; no model server runs.
"""

from contextlib import nullcontext
from types import MappingProxyType, SimpleNamespace
import pytest
from agent import model_call_policy as adapters
from gateway.config import Platform
from gateway.run_turn_runner import TurnRunner
from gateway.session_identity import RoutingIdentity
from hermes_cli.model_call_policy import _policy_payload

REQUEST = {"model": "synthetic-model", "messages": []}
KEY = "synthetic:shared-thread"
FIELDS = ("profile", "workspace", "conversation_key", "boundary_epoch")


class OwnedDB:
    def __init__(self, path, epoch):
        self.db_path, self.epoch, self.reads = path, epoch, []

    def get_session(self, session_id):
        return {"source": "discord"}

    def latest_conversation_boundary(self, session_key, source):
        self.reads.append((session_key, source))
        if isinstance(self.epoch, BaseException):
            raise self.epoch
        return self.epoch


@pytest.fixture
def make_turn(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_PROFILE_NAME", "process-default")
    monkeypatch.setenv("HERMES_PROFILE", "process-default")
    monkeypatch.setattr(
        "hermes_cli.lifecycle.has_hook", lambda name: name == "pre_model_call_policy"
    )
    monkeypatch.setattr(
        "gateway.session_policy.policy_for_source",
        lambda runner, source: source.fixture_policy,
    )
    monkeypatch.setattr(
        "gateway.session_policy.policy_scope", lambda *args, **kwargs: nullcontext()
    )
    monkeypatch.setattr(
        "gateway.session_policy.bind_turn_workspace", lambda *args: None
    )

    def build(
        callback,
        *,
        profile="routed-profile",
        workspace="/synthetic/project",
        epoch=7,
        author="actor-a",
        foreign_db=False,
    ):
        home = tmp_path / profile
        identity = RoutingIdentity(
            "receiving-bot", profile, tmp_path / "transport", home
        )
        source = SimpleNamespace(
            _identity=identity,
            platform=Platform.DISCORD,
            user_id=author,
            fixture_policy=SimpleNamespace(cwd=workspace),
        )
        db = OwnedDB((tmp_path / "foreign" if foreign_db else home) / "state.db", epoch)
        turn = object.__new__(TurnRunner)
        turn._runner = SimpleNamespace(_session_db=SimpleNamespace(_db=db))
        turn._ctx = SimpleNamespace(
            source=source,
            session_key=KEY,
            session_id="physical-session",
            run_generation=999,
        )
        turn._run_sync_scoped = callback
        return turn, db

    return build


@pytest.fixture
def agent():
    return SimpleNamespace(
        model="synthetic-model",
        provider="custom",
        api_mode="chat_completions",
        base_url="https://synthetic.example/v1",
        session_id="cached-physical",
        platform="discord",
    )


def payload(agent, kind="main"):
    if kind == "main":
        metadata = adapters._main_metadata(agent, REQUEST)
    else:
        metadata = adapters._aux_metadata(
            SimpleNamespace(base_url=agent.base_url),
            REQUEST,
            {"provider": "custom", "api_mode": "chat_completions"},
        )
    return _policy_payload(REQUEST, **metadata)


def projection(value):
    return {key: value.get(key) for key in FIELDS}


@pytest.mark.parametrize("kind", ["main", "auxiliary"])
def test_current_turn_owns_metadata_even_when_agent_is_reused(make_turn, agent, kind):
    seen = []
    for profile, workspace, epoch in [
        ("owned-a", "/synthetic/a", 3),
        ("owned-b", "/synthetic/b", 4),
    ]:
        turn, db = make_turn(
            lambda: seen.append(payload(agent, kind)) or {},
            profile=profile,
            workspace=workspace,
            epoch=epoch,
        )
        turn.run_sync()
        assert projection(seen[-1]) == dict(
            profile=profile,
            workspace=workspace,
            conversation_key=KEY,
            boundary_epoch=epoch,
        )
        assert db.reads == [(KEY, "discord")]
    outside = payload(agent, kind)
    assert outside["profile"] == "process-default"
    assert "conversation_key" not in outside


def test_author_change_does_not_rotate_shared_conversation(make_turn, agent):
    seen = []
    for author in ("actor-a", "actor-b"):
        turn, _db = make_turn(lambda: seen.append(payload(agent)) or {}, author=author)
        turn.run_sync()
    expected = dict(
        profile="routed-profile",
        workspace="/synthetic/project",
        conversation_key=KEY,
        boundary_epoch=7,
    )
    assert [projection(value) for value in seen] == [expected, expected]


@pytest.mark.parametrize(
    "epoch", [None, True, "7", -1, RuntimeError("synthetic DB failure")]
)
def test_missing_or_invalid_durable_epoch_stays_unknown_not_run_generation(
    make_turn, agent, epoch
):
    seen = []
    turn, _db = make_turn(lambda: seen.append(payload(agent)) or {}, epoch=epoch)
    turn.run_sync()
    assert projection(seen[0]) == dict(
        profile="routed-profile",
        workspace="/synthetic/project",
        conversation_key=KEY,
        boundary_epoch=None,
    )


def test_foreign_profile_db_is_not_queried_for_the_epoch(make_turn, agent):
    seen = []
    turn, db = make_turn(lambda: seen.append(payload(agent)) or {}, foreign_db=True)
    turn.run_sync()
    assert projection(seen[0]) == dict(
        profile="routed-profile",
        workspace="/synthetic/project",
        conversation_key=KEY,
        boundary_epoch=None,
    )
    assert db.reads == []


def test_worker_uses_captured_immutable_context_and_restores_current_turn(
    make_turn, agent
):
    saved, seen = {}, []

    def capture():
        scope = adapters._main_metadata(agent, REQUEST).get("runtime_context")
        assert isinstance(scope, MappingProxyType)
        with pytest.raises(TypeError):
            scope["profile"] = "not-owned"
        saved["target"] = adapters._context_thread_target(
            lambda: seen.append(payload(agent))
        )
        return {}

    first, _db = make_turn(
        capture, profile="owned-a", workspace="/synthetic/a", epoch=3
    )
    first.run_sync()

    def consume():
        saved["target"]()
        seen.append(payload(agent))
        return {}

    second, _db = make_turn(
        consume, profile="owned-b", workspace="/synthetic/b", epoch=4
    )
    second.run_sync()
    assert [projection(value) for value in seen] == [
        dict(
            profile="owned-a",
            workspace="/synthetic/a",
            conversation_key=KEY,
            boundary_epoch=3,
        ),
        dict(
            profile="owned-b",
            workspace="/synthetic/b",
            conversation_key=KEY,
            boundary_epoch=4,
        ),
    ]
    assert "conversation_key" not in payload(agent)


def test_exception_in_turn_restores_the_context_token(make_turn, agent):
    seen = []

    def fail():
        seen.append(payload(agent))
        raise RuntimeError("synthetic turn failure")

    turn, _db = make_turn(fail)
    with pytest.raises(RuntimeError, match="synthetic turn failure"):
        turn.run_sync()
    assert projection(seen[0]) == dict(
        profile="routed-profile",
        workspace="/synthetic/project",
        conversation_key=KEY,
        boundary_epoch=7,
    )
    assert "conversation_key" not in payload(agent)


def test_characterization_real_owning_sqlite_epoch_is_bound(make_turn, agent):
    import sqlite3
    from hermes_state import SessionDB

    seen = []
    turn, _fixture_db = make_turn(lambda: seen.append(payload(agent)) or {})
    db = SessionDB(db_path=turn._ctx.source._identity.store_path)
    try:
        db.create_session("physical-session", "discord")
        # Seed durable fixture data, then exercise the real SessionDB read contract.
        with sqlite3.connect(db.db_path) as connection:
            connection.execute(
                "INSERT INTO conversation_generations (source, session_key, generation) VALUES (?, ?, ?)",
                ("discord", KEY, 7),
            )
        turn._runner._session_db = SimpleNamespace(_db=db)
        turn.run_sync()
        assert projection(seen[0]) == dict(
            profile="routed-profile",
            workspace="/synthetic/project",
            conversation_key=KEY,
            boundary_epoch=7,
        )
    finally:
        db.close()
