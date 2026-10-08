import io

import pytest
from rich.console import Console

from lemonaid.brief import attached, colors
from lemonaid.config import PlaceRoot
from lemonaid.inbox import db
from lemonaid.places import inbox_cleanup, ownership, target, toss_cli, toss_warning


def _target(tmp_path, session="closing", partial=False):
    place = ownership.Place("feat", PlaceRoot(path=tmp_path, destroy="release {key}"), tmp_path)
    return target.TossTarget(
        "" if partial else session,
        [place],
        place,
        {} if partial else {"@1": []},
        {"@2": []} if partial else {},
        [],
    )


def _row(conn, tmp_path, channel, state, tty="/dev/closing", **metadata):
    row = db.add(
        conn,
        channel,
        "",
        name=f"lemon {channel}",
        metadata={
            "tty": tty,
            "cwd": str(tmp_path),
            **metadata,
        },
    )
    path = tmp_path / f"{row.id}.md"
    path.write_text(f"# {channel}\n\nStatus: {state}\n")
    attached.attach(conn, channel, path)
    return row


@pytest.mark.parametrize("partial", [False, True])
def test_only_affected_actionable_lemons_are_named(monkeypatch, tmp_path, partial):
    monkeypatch.setattr(inbox_cleanup.tmux.navigation, "session_ttys", lambda s: {"/dev/closing"})
    monkeypatch.setattr(inbox_cleanup.windows, "ttys", lambda ws: {"/dev/closing"})
    with db.connect() as conn:
        for state in ("merge", "approve", "blocked", "alert", "working", "done", "review"):
            _row(conn, tmp_path, state, state)
        _row(conn, tmp_path, "survivor", "merge", tty="/dev/elsewhere")
        _row(conn, tmp_path, "other-server", "alert", tmux_socket="/other/socket")
        _row(conn, tmp_path, "codex:daemon", "blocked", tty="")
        _row(conn, tmp_path.parent, "codex:outside", "merge", tty="")

    assert toss_warning.affected(_target(tmp_path, partial=partial)) == [
        (f"lemon {state}", state) for state in ("alert", "blocked", "approve", "merge")
    ] + [("lemon codex:daemon", "blocked")]


@pytest.mark.parametrize("state", ["merge", "approve", "blocked", "alert"])
def test_warning_colors_and_literal_names(monkeypatch, tmp_path, state):
    output = io.StringIO()
    console = Console(file=output, force_terminal=True, color_system="truecolor", no_color=False)
    monkeypatch.setattr(toss_warning, "Console", lambda **kwargs: console)
    monkeypatch.setattr(toss_warning, "affected", lambda doomed: [("[bold] lemon", state)])
    toss_warning.show(_target(tmp_path))
    rendered = output.getvalue()
    assert "[bold] lemon" in rendered
    rgb = console.get_style(colors.status_text_style(state)).color.get_truecolor()
    assert f"38;2;{rgb.red};{rgb.green};{rgb.blue}" in rendered
    assert f"({state})" in rendered


@pytest.mark.parametrize("answer,confirmed", [("", False), ("n", False), ("yes", True)])
def test_protected_warning_precedes_default_no_prompt(
    monkeypatch, tmp_path, capsys, answer, confirmed
):
    monkeypatch.setattr(toss_warning, "affected", lambda doomed: [("ready lemon", "merge")])

    def respond(prompt):
        assert "ready lemon (merge)" in capsys.readouterr().err
        assert "[y/N]" in prompt
        return answer

    monkeypatch.setattr("builtins.input", respond)
    assert toss_cli._confirmed(_target(tmp_path), {}) is confirmed


def test_missing_brief_does_not_break_confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr(inbox_cleanup.tmux.navigation, "session_ttys", lambda s: {"/dev/closing"})
    monkeypatch.setattr(inbox_cleanup.windows, "ttys", lambda ws: set())
    with db.connect() as conn:
        row = _row(conn, tmp_path, "missing", "merge")
        (tmp_path / f"{row.id}.md").unlink()
    assert toss_warning.affected(_target(tmp_path)) == []
