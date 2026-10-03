"""`--self` inside a sandbox that can't reach tmux: the harness's environment names the lemon."""

import argparse
import contextlib
import json
import os
from pathlib import Path

import pytest

from lemonaid.brief import child_cli, cli, lemon, write_cli
from lemonaid.inbox import db, decorate_cli

THREAD = "01a0d8ce-0000-7000-8000-000000000001"
CHANNEL = f"codex:{THREAD}"


@pytest.fixture(autouse=True)
def _sandboxed_codex(monkeypatch):
    """A pane tmux won't answer about (conftest points $TMUX at no server), and a Codex thread."""
    monkeypatch.setenv("TMUX_PANE", "%387")
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD)


def _codex_row() -> None:
    with db.connect() as conn:
        db.add(conn, CHANNEL, "", metadata={"tmux_session": "work", "tmux_window": "2"})


def _brief(name: str = "task") -> Path:
    path = Path(os.environ["LEMONAID_BRIEFS_DIR"]) / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: working\n\n## Now\n\n### Next\n\n- Start {name}.\n")
    return path


def _run(capsys, parsers, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    parsers(parser.add_subparsers())
    args = parser.parse_args([*argv, "--json"])
    with contextlib.suppress(SystemExit):
        args.func(args)

    return json.loads(capsys.readouterr().out)


def test_brief_verbs_find_the_codex_thread_without_tmux(capsys):
    _codex_row()
    brief = _brief()

    attached = _run(capsys, write_cli.add_parsers, "attach", "--self", str(brief))
    added = _run(capsys, write_cli.add_parsers, "waiter", "add", "--self", "lemonaid inbox watch")
    checked = _run(capsys, write_cli.add_parsers, "check", "--self")

    assert attached["channel"] == CHANNEL
    assert added["error"] is None
    assert "lemonaid inbox watch" in brief.read_text()
    assert checked["error"] is None and checked["path"] == str(brief)


def test_a_thread_with_no_inbox_row_gets_no_brief(capsys):
    refused = _run(capsys, write_cli.add_parsers, "attach", "--self", str(_brief()))

    assert refused["error"] == f"No inbox session on channel {CHANNEL!r}"


def test_inbox_emoji_finds_the_codex_thread_without_tmux(capsys):
    _codex_row()

    set_emoji = _run(capsys, decorate_cli.add_parsers, "emoji", "--self", "🦫")

    assert set_emoji == {"channel": CHANNEL, "emoji": "🦫", "error": None}


def test_a_thread_with_no_inbox_row_is_not_decorated(capsys):
    refused = _run(capsys, decorate_cli.add_parsers, "rename", "--self", "tenant views")

    assert refused["error"] == f"No inbox session {CHANNEL!r}"


def test_a_child_brief_records_the_parents_tmux_session_from_its_row(capsys):
    _codex_row()
    _run(capsys, write_cli.add_parsers, "attach", "--self", str(_brief()))

    with db.connect() as conn:
        lemon_id = lemon.own_id(conn)

    assert child_cli._parent("self") == (lemon_id, "work")


def test_show_with_no_session_shows_only_the_callers_brief(capsys, monkeypatch):
    _codex_row()
    _run(capsys, write_cli.add_parsers, "attach", "--self", str(_brief()))
    with db.connect() as conn:
        db.add(conn, "claude:neighbor", "", metadata={"tmux_session": "work", "tmux_window": "2"})
    _run(
        capsys,
        write_cli.add_parsers,
        "attach",
        "--channel",
        "claude:neighbor",
        str(_brief("other")),
    )
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["brief", "show"])

    args.func(args)

    shown = capsys.readouterr().out
    assert "Start task." in shown and "Start other." not in shown


def _show(capsys, *argv: str) -> tuple[str, str]:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["brief", "show", *argv])
    with contextlib.suppress(SystemExit):
        args.func(args)

    captured = capsys.readouterr()
    return captured.out, captured.err


def test_show_self_shows_the_callers_brief_even_when_a_session_is_known(capsys, monkeypatch):
    _codex_row()
    _run(capsys, write_cli.add_parsers, "attach", "--self", str(_brief()))
    with db.connect() as conn:
        db.add(conn, "claude:neighbor", "", metadata={"tmux_session": "work", "tmux_window": "2"})
    _run(
        capsys,
        write_cli.add_parsers,
        "attach",
        "--channel",
        "claude:neighbor",
        str(_brief("other")),
    )
    monkeypatch.setattr(cli.session, "current_session", lambda: "work")

    shown, _ = _show(capsys, "--self")

    assert "Start task." in shown and "Start other." not in shown


def test_show_self_with_no_attached_brief_says_so(capsys):
    _codex_row()

    shown, error = _show(capsys, "--self")

    assert shown == "" and "No brief is attached" in error
