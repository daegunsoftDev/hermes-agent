"""Immutable host-owned model-call metadata, not backend authorization.

Only admitted Python callers bind this context; request JSON cannot bind it.
Workspace/epoch may be unknown. Legacy calls remain unscoped. This does not
change cache keys, implement serialized-wire fencing, or supply a revision ID.
"""

from __future__ import annotations
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType

_CURRENT: ContextVar[Mapping[str, str | int | None] | None] = ContextVar(
    "model_call_context", default=None
)


def freeze_model_call_context(*, profile, workspace, conversation_key, boundary_epoch):
    for name, value in (("profile", profile), ("conversation_key", conversation_key)):
        if type(value) is not str or not value.strip():
            raise ValueError(f"{name} must be a nonempty primitive string")
    if workspace is not None and (type(workspace) is not str or not workspace.strip()):
        raise ValueError("workspace must be a nonempty primitive string or None")
    if boundary_epoch is not None:
        if type(boundary_epoch) is not int:
            raise TypeError(
                "boundary_epoch must be an integer, not bool or coerced text"
            )
        if boundary_epoch < 0:
            raise ValueError("boundary_epoch must be nonnegative")
    return MappingProxyType(
        {
            "profile": profile,
            "workspace": workspace,
            "conversation_key": conversation_key,
            "boundary_epoch": boundary_epoch,
        }
    )


@contextmanager
def model_call_context(snapshot: Mapping | None) -> Iterator[None]:
    frozen = None if snapshot is None else freeze_model_call_context(**snapshot)
    token = _CURRENT.set(frozen)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def capture_model_call_context():
    """Capture immutable primitives for this call; existing worker copy/rebind preserves them."""
    return _CURRENT.get()
