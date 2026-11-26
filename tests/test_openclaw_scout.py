"""Mail to an OpenClaw lemon: `tell` starts its scout, and the scout turns batches into gateway turns."""

import argparse
import json
import stat

import pytest

import lemonaid.watch.cli
from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.front_end import chat
from lemonaid.inbox import db
from lemonaid.messages import cli, recipient, store, tell_delivery, waiter
from lemonaid.openclaw import sessions
from lemonaid.watch import hosted_scout, openclaw_scout, scout_roster, wait_cli, wait_state

KEY = "agent:garden:matrix:channel:!g4rd3n:grove.example"
CHANNEL = f"openclaw:{KEY}"


@pytest.fixture(autouse=True)
def _sender(monkeypatch):
    for name in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX_PANE", "CODEX_HOME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:sender")
    monkeypatch.setattr(tell_delivery.service, "ensure_running", lambda: None)


def _attach() -> str:
    path = brief_store.briefs_dir() / "garden.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Barn deck\n")
    with db.connect() as conn:
        db.register_working(
            conn,
            CHANNEL,
            "",
            metadata={"session_key": KEY, "cwd": "/srv/garden"},
            switch_source=chat.NAME,
        )
        attached.attach(conn, CHANNEL, path)
        return identity.ensure(conn, path)


def _tell(target: str) -> int:
    parser = argparse.ArgumentParser()
    cli.add_tell_parser(parser.add_subparsers())
    args = parser.parse_args(["tell", target, "hello"])
    try:
        args.func(args)
    except SystemExit as exit:
        return int(exit.code or 0)

    return 0


def test_tell_starts_the_scout_and_a_listening_lemon_reads_it(capsys, monkeypatch):
    lemon_id = _attach()
    started = []

    def ensure(channel, lemon, cwd):
        started.append((channel, lemon, cwd))
        return True

    monkeypatch.setattr(openclaw_scout, "ensure", ensure)
    with waiter.armed(store.mailbox_for_id(lemon_id)):
        assert _tell(CHANNEL) == 0

    assert started == [(CHANNEL, lemon_id, "/srv/garden")]
    assert "listening" in capsys.readouterr().err


def test_an_openclaw_lemon_without_a_scout_is_deaf_not_dead():
    _attach()
    with db.connect() as conn:
        row = db.get_by_channel(conn, CHANNEL, unread_only=False)
    assert row is not None

    state = recipient.classify(CHANNEL, row, None, False, 0.0)

    assert state.state == recipient.DEAF
    assert recipient.confirmed(row, state) == state


def test_ensure_registers_the_scout_with_the_host(monkeypatch):
    lemon_id = _attach()
    armed = iter([False, False, True])
    monkeypatch.setattr(wait_state, "is_armed", lambda lemon, grace=0: next(armed))

    assert openclaw_scout.ensure(CHANNEL, lemon_id, "/srv/garden") is True

    registration = scout_roster.read(lemon_id)
    assert registration is not None
    assert (registration.channel, registration.thread) == (CHANNEL, "")


@pytest.fixture
def fake_openclaw(tmp_path, monkeypatch):
    """An `openclaw` that records each call and answers like a gateway that ran the turn."""
    log = tmp_path / "calls.jsonl"
    cli_path = tmp_path / "openclaw"
    cli_path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1] == 'sessions':\n"
        f"    print(json.dumps({{'sessions': [{{'key': {KEY!r}}}]}}))\n"
        "else:\n"
        "    print(json.dumps({'ok': True, 'status': 'ok'}))\n"
    )
    cli_path.chmod(cli_path.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(sessions, "cli", lambda: str(cli_path))
    return log


def test_the_hosted_scout_delivers_a_batch_as_one_gateway_turn(fake_openclaw):
    registration = scout_roster.Registration("Barn.deck", CHANNEL, "", "/srv", "", "t")

    found = hosted_scout._harness(registration)
    assert not isinstance(found, str)
    assert found.alive() is True
    assert found.writer == f"openclaw-{KEY}"
    found.output("mail from HQ")

    calls = [json.loads(line) for line in fake_openclaw.read_text().splitlines()]
    turn = next(argv for argv in calls if argv[:3] == ["gateway", "call", "agent"])
    assert "--expect-final" not in turn  # waiting out the turn would stall the scout's heartbeat
    params = json.loads(turn[turn.index("--params") + 1])
    assert params["sessionKey"] == KEY
    assert "mail from HQ" in params["message"]


def test_watch_self_push_inside_openclaw_starts_the_openclaw_scout(monkeypatch, tmp_path):
    lemon_id = _attach()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".openclaw/agents/garden/agent/codex-home"))
    monkeypatch.setenv("CODEX_THREAD_ID", "01a2-thread")
    monkeypatch.setenv("LEMONAID_CHANNEL", CHANNEL)
    started = []
    monkeypatch.setattr(
        openclaw_scout, "start", lambda channel, lemon, cwd: started.append((channel, lemon)) or 0
    )
    parser = argparse.ArgumentParser()
    lemonaid.watch.cli.setup_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["watch", "--self", "--push"])

    assert wait_cli.run(args) == 0
    assert started == [(CHANNEL, lemon_id)]


def test_ensure_moves_the_scout_to_the_session_the_brief_moved_to(monkeypatch):
    lemon_id = _attach()
    old = "openclaw:agent:main:matrix:channel:!old:grove.example"
    scout_roster.register(lemon_id, old, "", "/srv")
    monkeypatch.setattr(wait_state, "is_armed", lambda lemon, grace=0: True)  # the old scout's lock

    assert openclaw_scout.ensure(CHANNEL, lemon_id, "/srv/garden") is True

    registration = scout_roster.read(lemon_id)
    assert registration is not None and registration.channel == CHANNEL


def test_ensure_keeps_a_scout_already_serving_the_session(monkeypatch):
    lemon_id = _attach()
    scout_roster.register(lemon_id, CHANNEL, "", "/srv/garden")
    token = scout_roster.read(lemon_id).token
    monkeypatch.setattr(wait_state, "is_armed", lambda lemon, grace=0: True)

    assert openclaw_scout.ensure(CHANNEL, lemon_id, "/srv/garden") is True
    assert scout_roster.read(lemon_id).token == token


def test_a_session_counts_as_mid_turn_from_the_moment_the_scout_sends_it_a_batch(
    fake_openclaw,
):
    found = openclaw_scout.harness(CHANNEL)
    assert found.latest_turn() is None  # the fake gateway lists no turn

    found.deliver("mail from HQ")

    assert found.latest_turn().running is True
