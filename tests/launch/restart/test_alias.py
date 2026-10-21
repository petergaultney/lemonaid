import dataclasses

import pytest

from lemonaid.claude import launch_args
from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.launch.restart import coordinator, native, pane, planning, process, state
from lemonaid.messages import codex_delivery, store
from lemonaid.watch import delivery, file_events, registry
from tests import test_codex_alias_coordination as alias_fixtures
from tests.test_codex_duplicate_channels import _ROOT

from . import shared

alias = alias_fixtures.alias
setup = alias_fixtures.setup


def test_fresh_alias_observation_supports_preflight_and_resumed_ownership(
    alias, tmp_path, monkeypatch
):
    channel, _, _ = alias
    target = dataclasses.replace(shared.TARGET, cwd=str(tmp_path))
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
        db.repair_location(
            conn, row, {"tty": target.tty, "cwd": target.cwd, "tmux_socket": target.socket}
        )
    live = [shared.SOURCE]
    monkeypatch.setattr(process, "ancestry", lambda *a: [live[0], shared.ROOT])
    monkeypatch.setattr(process, "inspect", lambda *a: shared.ROOT)
    monkeypatch.setattr(process, "same", lambda *a: True)
    monkeypatch.setattr(process, "on_tty", lambda *a: [live[0], shared.ROOT])
    monkeypatch.setattr(process, "descendants", lambda *a: [])
    monkeypatch.setattr(launch_args, "argv", lambda *a: ["codex", "--no-daemon"])
    monkeypatch.setattr(registry, "mine", lambda *a: [])
    monkeypatch.setattr(pane, "locate", lambda *a: target)
    monkeypatch.setattr(pane, "exit_option", lambda *a: "")
    monkeypatch.setattr(pane, "preserve", lambda *a: None)
    monkeypatch.setattr(pane, "restore", lambda *a: None)
    monkeypatch.setattr(pane, "check", lambda p: p)
    monkeypatch.setattr(process, "terminate", lambda *a: None)
    native.observe({"thread_id": _ROOT}, "codex")
    assert native.binding(channel)["session_id"] == _ROOT
    assert state.read("native-" + state.key("codex:" + _ROOT) + ".json") is None
    with db.connect() as conn:
        plan = planning.build(conn, "codex:" + _ROOT, Config())
    assert plan["channel"] == channel
    assert _ROOT in plan["line"]
    token = state.reserve(plan)

    def replace(*a):
        live[0] = dataclasses.replace(shared.SOURCE, pid=102)
        native.observe({"thread_id": _ROOT}, "codex")
        return target

    monkeypatch.setattr(pane, "replace", replace)
    coordinator.run(token)
    assert state.get(token)["phase"] == "started"
    assert native.binding(channel)["identity"]["pid"] == 102
    assert not state.blocked(channel)


def test_alias_reservation_holds_inbox_delivery_until_release(alias, monkeypatch):
    channel, _, lemon_id = alias
    inbox = store.inbox_for_id(lemon_id)
    pending = store.send(inbox, "hold me", "test")
    queued = []
    monkeypatch.setattr(codex_delivery, "_queue", lambda thread, *a: queued.append(thread))
    token = state.reserve({"channel": channel})
    assert codex_delivery.deliver_next(inbox, _ROOT) is None
    assert pending.exists() and not queued
    state.update(token, "started")
    assert codex_delivery.deliver_next(inbox, _ROOT) is not None
    assert queued == [_ROOT]
    assert not pending.exists()


def test_alias_reservation_holds_direct_watch_delivery_until_release(alias, tmp_path, monkeypatch):
    channel, _, _ = alias
    queued = []
    monkeypatch.setattr(delivery.subprocess, "run", lambda args, **kw: queued.append(args))
    file = tmp_path / "watched"
    file.write_text("before")
    cursor_dir = tmp_path / "cursors"
    watch = file_events.open_watch(cursor_dir, [file], "", 0)
    before = watch.reported_path.read_text()
    output = delivery.to_codex(_ROOT, "watch file", "continue")
    file.write_text("after")
    token = state.reserve({"channel": channel})
    with pytest.raises(ValueError, match="remain pending"):
        file_events.poll(watch, output)
    assert not queued
    assert watch.reported_path.read_text() == before
    state.update(token, "started")
    rearmed = file_events.open_watch(cursor_dir, [file], "", 0)
    assert file_events.poll(rearmed, output)
    assert queued[0][queued[0].index("--thread") + 1] == _ROOT
