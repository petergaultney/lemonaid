"""A persistent thread and its attached notification alias share coordination state."""

import argparse

import pytest

from lemonaid.brief import attached, identity, waiters
from lemonaid.claude import waiter_check
from lemonaid.inbox import db
from lemonaid.messages import codex_delivery, service, waiter
from lemonaid.messages import store as messages
from lemonaid.watch import (
    batch_wait,
    brief_record,
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
    assert waiter_check.attached_brief({"session_id": _ROOT}, "codex") == path
    reason = waiter_check.reason_to_block({"session_id": _ROOT}, 0, "codex")
    assert f"No unified watcher is armed for {lemon_id}" in reason
    monkeypatch.setattr(wait_state, "is_armed", lambda owner, grace: owner == lemon_id)
    assert waiter_check.reason_to_block({"session_id": _ROOT}, 0, "codex") == ""


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
