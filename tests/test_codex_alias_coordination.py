"""A persistent thread and its attached notification alias share coordination state."""

import argparse
import json

import pytest

from lemonaid.brief import attached, identity, waiters
from lemonaid.hooks import stop_check
from lemonaid.inbox import db
from lemonaid.messages import codex_delivery, service, waiter
from lemonaid.messages import store as messages
from lemonaid.watch import (
    batch_wait,
    brief_record,
    codex_waiter,
    cursors,
    delivery,
    registry,
    wait_cli,
    wait_state,
)
from tests import test_codex_duplicate_channels
from tests.test_codex_duplicate_channels import (
    _LOCATION,
    _ROOT,
    _TRANSIENT,
    _row,
)

setup = test_codex_duplicate_channels.setup
_REAL_SPAWN = codex_waiter._spawn


@pytest.fixture
def alias(setup, monkeypatch):
    with db.connect() as conn:
        row = _row(conn, _TRANSIENT, _LOCATION, attach=True)
        db.repair_location(conn, row, {"session_id": _ROOT, "session_path": str(setup)})
        path = attached.by_channel(conn, [row.channel])[row.channel]
        lemon_id = identity.ensure(conn, path)
    with path.open("a") as stream:
        stream.write("\n## Watching\n\n- `lemonaid watch file --wait /tmp/task`\n")
    monkeypatch.setenv("CODEX_THREAD_ID", _ROOT)
    monkeypatch.delenv("LEMONAID_CHANNEL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    return row.channel, path, lemon_id


def test_unified_watch_arms_alias_inbox_and_delivers_to_real_thread(alias, monkeypatch):
    channel, path, lemon_id = alias
    args = argparse.Namespace(
        codex_thread=None,
        channel="",
        status=False,
        interval=0.01,
        quiet=0,
        push=False,
        foreground=False,
    )
    # None is the bare --codex-thread form and reads CODEX_THREAD_ID.
    monkeypatch.setattr(delivery, "codex_setup_problem", lambda: "")
    queued = []
    monkeypatch.setattr(
        delivery, "to_codex", lambda thread, *args: lambda text: queued.append((thread, text))
    )

    def batch(*args, **kwargs):
        assert args[0] == path
        assert args[1] == messages.inbox_for_id(lemon_id)
        assert args[2] == cursors.root() / lemon_id
        assert args[5]()  # still attached to the alias, not the raw thread
        assert waiter.is_armed(args[1])
        assert wait_state.is_armed(lemon_id)
        assert registry.mine(channel, "wait")[0].channel == channel
        status = argparse.Namespace(**{**vars(args_namespace), "status": True})
        assert wait_cli.run(status) == 0
        args[4]("one pending batch")

    args_namespace = args
    monkeypatch.setattr(batch_wait, "wait", batch)
    assert wait_cli.run(args) == 0
    assert queued == [(_ROOT, "one pending batch")]
    assert not waiter.is_armed(messages.inbox_for_id(lemon_id))
    assert not wait_state.is_armed(lemon_id)


def test_direct_watch_records_and_registers_under_same_alias(alias, tmp_path):
    channel, path, lemon_id = alias
    assert registry.owner_channel(codex_thread=_ROOT) == channel
    assert registry.owner_channel() == channel
    assert registry.owner_channel(explicit="codex:other") == "codex:other"
    assert cursors.owner("Reviewer (X)", _ROOT) == lemon_id
    assert cursors.owner("Other signature") == lemon_id
    command = ["lemonaid", "watch", "file", "--wait", str(tmp_path / "task"), "--codex-thread"]
    args = argparse.Namespace(invocation=command, channel="")
    assert brief_record.record(args, "file", thread=_ROOT) == ""
    assert any("--codex-thread" in item for item in waiters.commands(path.read_text()))
    with registry.registered(
        "file", ("task",), registry.owner_channel(codex_thread=_ROOT), "watch"
    ):
        # stop --self uses the environment path; it must find the explicit-thread waiter.
        assert registry.mine(registry.owner_channel(), "file")[0].channel == channel


def test_alias_inbox_delivery_queues_real_thread(alias, monkeypatch):
    channel, path, lemon_id = alias
    assert codex_delivery.own_thread(channel) == _ROOT
    assert codex_delivery.own_thread("codex:other") == ""
    inbox = messages.inbox_for_id(lemon_id)
    with db.connect() as conn:
        assert list(service.codex_recipients(conn)) == [(inbox, _ROOT)]
    messages.send(inbox, "review this", "sender.IndexElf")
    queued = []
    monkeypatch.setattr(
        codex_delivery, "_queue", lambda thread, path, message: queued.append(thread)
    )
    assert codex_delivery.deliver_next(inbox, codex_delivery.own_thread(channel)) is not None
    assert queued == [_ROOT]
    assert messages.peek_next(inbox) is None


def test_stop_hook_finds_alias_and_requires_its_unified_watcher(alias, monkeypatch):
    channel, path, lemon_id = alias
    assert stop_check.attached_brief({"session_id": _ROOT}, "codex") == path
    reason = stop_check.reason_to_block({"session_id": _ROOT}, 0, "codex")
    assert f"No unified watcher is armed for {lemon_id}" in reason
    monkeypatch.setattr(wait_state, "is_armed", lambda owner, grace: owner == lemon_id)
    assert stop_check.reason_to_block({"session_id": _ROOT}, 0, "codex") == ""


def test_stop_self_finds_waiter_registered_before_alias_fix(alias):
    channel, _, _ = alias
    with registry.registered("doc", ("review",), f"codex:{_ROOT}", "watch"):
        assert registry.mine(channel, "doc")[0].channel == f"codex:{_ROOT}"
        assert registry.mine("codex:unrelated") == []


def test_handoff_reads_alias_owner_transcript(alias, setup, monkeypatch):
    from lemonaid.brief import handoff_codex

    channel, _, _ = alias
    looked_up = []
    monkeypatch.setattr(
        handoff_codex.codex_watcher,
        "get_session_path",
        lambda thread, cwd: looked_up.append(thread) or setup,
    )
    with db.connect() as conn:
        assert not handoff_codex.has_ready_marker(conn, {"source": channel, "token": "token"})
        handoff_codex.phrases(conn, {"source": channel, "target": ""})
    assert looked_up == [_ROOT, _ROOT]


def test_explicit_raw_channel_names_alias_for_brief_tell_and_doctor(alias, monkeypatch):
    from lemonaid.brief import lemon
    from lemonaid.lemon_facts import cli as doctor_cli
    from lemonaid.messages import cli as messages_cli
    from lemonaid.messages import recipient

    channel, path, lemon_id = alias
    raw = f"codex:{_ROOT}"
    with db.connect() as conn:
        assert lemon.self_channel(conn, raw) == channel
        assert lemon.own_id(conn, raw) == lemon_id
        assert lemon.attachment(conn, raw).path == path
        assert doctor_cli._scope(
            conn, argparse.Namespace(lemons=[raw], children=False, orphans=False, all=False)
        ) == [lemon_id]
    monkeypatch.setattr(service, "ensure_running", lambda: None)
    monkeypatch.setattr(
        recipient, "probe", lambda *args: recipient.State(recipient.LISTENING, "armed")
    )
    messages_cli.cmd_tell(
        argparse.Namespace(parent=False, child="", target=raw, message="alias target", channel="")
    )
    assert "alias target" in messages.peek_next(messages.inbox_for_id(lemon_id))[1]


def test_stop_before_first_notify_resolves_unbound_alias_and_blocks(setup, monkeypatch, capsys):
    from lemonaid import handlers

    with db.connect() as conn:
        row = _row(conn, _TRANSIENT, _LOCATION, attach=True)
        path = attached.by_channel(conn, [row.channel])[row.channel]
        identity.ensure(conn, path)
    with path.open("a") as stream:
        stream.write("\n## Watching\n- `lemonaid watch file --wait /tmp/task`\n")
    monkeypatch.setattr(handlers, "codex_tmux_locations", lambda: {_ROOT: [_LOCATION]})
    stop_check.handle(json.dumps({"session_id": _ROOT}), grace=0, harness="codex")
    result = json.loads(capsys.readouterr().out)
    assert result["decision"] == "block"
    assert "No unified watcher is armed" in result["reason"]
    with db.connect() as conn:
        assert db.get(conn, row.id).metadata["session_id"] == _ROOT
        assert attached.by_channel(conn, [row.channel])[row.channel] == path


def test_inbox_restores_deaf_alias_watcher_using_real_root(alias, monkeypatch):
    from lemonaid.messages import recipient
    from lemonaid.watch import codex_waiter

    channel, _, lemon_id = alias
    started = []
    monkeypatch.setattr(recipient, "harness_alive", lambda row: True)
    monkeypatch.setattr(codex_waiter, "ensure", lambda *args: started.append(args))
    monkeypatch.setattr(codex_waiter.processes, "thread_ttys", lambda: {_ROOT: {_LOCATION["tty"]}})
    with db.connect() as conn:
        codex_waiter.restore(conn)
    assert started == [(channel, _ROOT, lemon_id)]


@pytest.mark.parametrize(
    "state",
    [
        "armed",
        "dead",
        "unknown",
        "archived",
        "unsubscribed",
        "mid-turn",
        "handoff",
        "unverified",
        "reused-tty",
    ],
)
def test_inbox_does_not_restore_other_codex_sessions(alias, monkeypatch, state):
    import time

    from lemonaid.messages import recipient
    from lemonaid.watch import codex_waiter

    channel, path, _ = alias
    monkeypatch.setattr(
        recipient, "harness_alive", lambda row: {"dead": False, "unknown": None}.get(state, True)
    )
    monkeypatch.setattr(wait_state, "is_armed", lambda lemon_id: state == "armed")
    monkeypatch.setattr(codex_waiter, "ensure", lambda *args: pytest.fail("unwanted watcher"))
    if state == "unsubscribed":
        path.write_text(path.read_text().split("## Watching")[0])
    with db.connect() as conn:
        if state == "archived":
            db.archive_channel(conn, channel, "test")
        if state == "mid-turn":
            db.record_turn(conn, channel, time.time())
        if state == "reused-tty":
            from lemonaid.codex import processes

            monkeypatch.setattr(processes, "thread_ttys", lambda: {"stranger": {_LOCATION["tty"]}})
        if state == "unverified":
            row = db.get_by_channel(conn, channel, unread_only=False)
            db.repair_location(conn, row, {"session_path": None})
        if state == "handoff":
            from lemonaid.brief import handoff_state

            handoff_state.request(
                conn, path, channel, "claude", "shared", "2", "@1", "%2", "codex", time.time() + 60
            )
        codex_waiter.restore(conn)


def test_detached_recovery_actually_arms_alias_inbox(alias, monkeypatch, tmp_path):
    import os
    import subprocess

    channel, path, lemon_id = alias
    target = tmp_path / "watched.txt"
    target.write_text("unchanged")
    path.write_text(
        path.read_text().split("## Watching")[0]
        + f"## Watching\n- `lemonaid watch file --wait {target}`\n"
    )
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake = fake_bin / "codex"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ["PATH"])
    started = []
    real_popen = subprocess.Popen

    def launch(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", launch)
    try:
        _REAL_SPAWN(channel, _ROOT)
        assert wait_state.is_armed(lemon_id, grace=5)
        assert waiter.is_armed(messages.inbox_for_id(lemon_id), grace=1)
        assert registry.mine(channel, "wait")
    finally:
        for process in started:
            process.terminate()
            process.wait(timeout=5)
    assert not wait_state.is_armed(lemon_id)
