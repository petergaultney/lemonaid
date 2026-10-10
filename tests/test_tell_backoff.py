"""`tell` stops starting a lemon that keeps dying, and says so."""

import argparse
import time

import pytest

from lemonaid import messages_config
from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db
from lemonaid.messages import autoresume, autoresume_tmux, cli, recipient, resume_log, store


@pytest.fixture(autouse=True)
def _sender(monkeypatch):
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:sender")
    monkeypatch.setattr(cli.service, "ensure_running", lambda: None)
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["-fish"])  # nothing runs there


@pytest.fixture
def started(monkeypatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(autoresume_tmux, "start", lambda row, config: calls.append("start") or "")
    return calls


def _attach() -> str:
    path = brief_store.briefs_dir() / "recipient.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# t\n\nStatus: working\n")
    with db.connect() as conn:
        db.add(conn, "claude:gone", "", metadata={"tty": "/dev/ttys900"}, switch_source="tmux")
        attached.attach(conn, "claude:gone", path)
        return identity.ensure(conn, path)


def _log(lemon_id: str, *entries: tuple[float, str]) -> None:
    inbox = store.inbox_for_id(lemon_id)
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / ".autoresumed").write_text(
        "".join(f"{time.time() - ago} {kind}\n" for ago, kind in entries)
    )


def _tell() -> int:
    parser = argparse.ArgumentParser()
    cli.add_tell_parser(parser.add_subparsers())
    args = parser.parse_args(["tell", "claude:gone", "hello"])
    try:
        args.func(args)
    except SystemExit as exit:
        return int(exit.code or 0)

    return 0


def test_three_starts_in_the_window_refuse_a_fourth(capsys, started):
    lemon_id = _attach()
    _log(lemon_id, (900, "start"), (600, "start"), (300, "start"))

    assert _tell() == 1
    assert started == []
    assert "is crash-looping and not responding" in capsys.readouterr().err
    with db.connect() as conn:
        assert "ALERT" in db.get_by_channel(conn, autoresume.CHANNEL, unread_only=False).message


def test_starts_older_than_the_window_do_not_count(started):
    lemon_id = _attach()
    _log(lemon_id, (3000, "start"), (2500, "start"), (2000, "start"))

    assert _tell() == 0
    assert started == ["start"]


def test_dying_soon_after_a_start_counts_as_a_failed_start(capsys, started):
    lemon_id = _attach()
    _log(lemon_id, (600, "start"), (90, "start"))  # dead again 90 seconds after the last start

    assert _tell() == 1
    assert started == []
    assert [entry.kind for entry in resume_log.entries(store.inbox_for_id(lemon_id))] == [
        "start",
        "start",
        "failed",
    ]


def test_starting_and_quick_death_windows():
    now = 1000.0
    log = [resume_log.Entry(now - 30, resume_log.START)]

    assert resume_log.starting(log, now)
    assert resume_log.died_quickly(log, now)
    assert not resume_log.starting(log, now + 60)
    assert not resume_log.died_quickly(log, now + 600)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({}, (3, 1200.0)),
        ({"autoresume_max": 5, "autoresume_window": "1h"}, (5, 3600.0)),
        ({"autoresume_max": 0, "autoresume_window": "soon"}, (3, 1200.0)),
    ],
)
def test_backoff_settings(data, expected):
    parsed = messages_config.parse(data)

    assert (parsed.autoresume_max, parsed.autoresume_window) == expected
