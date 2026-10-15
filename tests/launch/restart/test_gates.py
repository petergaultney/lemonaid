import argparse

import pytest

from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.launch.restart import gates, state
from lemonaid.messages import cli, codex_delivery, revive, store
from lemonaid.watch import registry

from . import shared


@pytest.mark.parametrize(
    "phase", ["planned", "quiescing", "stopping", "source-exited", "starting", "verifying"]
)
def test_tell_stays_pending_and_resume_delivery_registration_are_excluded(
    tmp_path, monkeypatch, phase
):
    with db.connect() as conn:
        _path, before, lemon_id, _transcript = shared.setup(conn, tmp_path)
        token = state.reserve(conn, {**shared.plan(tmp_path), "lemon_id": lemon_id})
        state.update(conn, token, phase)
    monkeypatch.setattr(
        codex_delivery, "_queue", lambda *args: pytest.fail("delivered during cutover")
    )
    monkeypatch.setattr(
        revive, "bring_back", lambda *args: pytest.fail("started competing harness")
    )
    args = argparse.Namespace(
        parent=False, child="", target=lemon_id, message="pending", channel="sender"
    )
    cli.cmd_tell(args)
    inbox = store.inbox_for_id(lemon_id)
    assert store.peek_next(inbox) is not None
    assert codex_delivery.deliver_next(inbox, shared.SESSION) is None
    assert revive.revive(before, inbox, True, Config(), "resume").kind == revive.STARTING
    with (
        pytest.raises(ValueError, match="registration"),
        registry.registered("wait", (lemon_id,), shared.CHANNEL, "lemonaid watch --self"),
    ):
        pytest.fail("registered an old-generation watcher")
    with db.connect() as conn:
        assert db.get_by_channel(conn, shared.CHANNEL, unread_only=False) == before


def test_old_delivery_cannot_cross_reservation(tmp_path):
    sent = []
    deliver = gates.deliver(shared.CHANNEL, sent.append)
    with db.connect() as conn:
        state.reserve(conn, shared.plan(tmp_path))
    with pytest.raises(ValueError, match="holds delivery"):
        deliver("pending event")
    assert not sent


def test_turn_start_gate_blocks_source_but_accepts_tokened_replacement(
    tmp_path, monkeypatch, capsys
):
    with db.connect() as conn:
        token = state.reserve(conn, shared.plan(tmp_path))
        state.update(conn, token, "verifying")
    payload = '{"session_id":"' + shared.SESSION + '"}'
    assert not gates.turn_start("codex", payload)
    assert '"decision": "block"' in capsys.readouterr().out
    monkeypatch.setenv("LEMONAID_RESTART_TOKEN", token)
    assert gates.turn_start("codex", payload)
