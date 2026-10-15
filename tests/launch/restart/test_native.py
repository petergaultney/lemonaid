import dataclasses

import pytest

from lemonaid.hooks import session_start
from lemonaid.inbox import db
from lemonaid.launch.restart import native, state

from . import shared

_harness_parent = native.harness_parent


def test_claude_hook_cannot_bind_to_a_codex_ancestor(monkeypatch):
    monkeypatch.setattr(native.process, "ancestry", lambda pid: [shared.SOURCE])
    assert _harness_parent("claude") is None
    assert _harness_parent("codex") == shared.SOURCE
    versioned = dataclasses.replace(shared.SOURCE, executable="/versions/2.1.300")
    monkeypatch.setattr(native.process, "ancestry", lambda pid: [versioned])
    assert _harness_parent("claude") == versioned


@pytest.mark.parametrize("phase", ["planned", "starting", "verifying", "complete"])
def test_session_start_defers_tool_use_only_for_its_verifying_operation(
    tmp_path, monkeypatch, phase
):
    with db.connect() as conn:
        token = state.reserve(conn, shared.plan(tmp_path))
        state.update(conn, token, phase)
    data = {"session_id": shared.SESSION}
    monkeypatch.setenv("LEMONAID_RESTART_TOKEN", token)
    assert native.verifying(data, "codex") == (phase in ("starting", "verifying"))
    if phase in ("starting", "verifying"):
        monkeypatch.setattr(native, "observe", lambda *args: True)
        context = session_start.context(data, "codex")
        assert "Do not use tools yet" in context
    monkeypatch.setenv("LEMONAID_RESTART_TOKEN", "stale")
    assert not native.verifying(data, "codex")
