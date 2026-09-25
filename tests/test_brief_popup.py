"""The popup: where it opens, and that its command stands on its own."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import rich.console

from lemonaid.brief import attached, cli, display, popup, render, target
from lemonaid.inbox import db


def test_the_fallback_pager_quits_on_escape_as_well_as_q():
    command = popup._less_command()

    assert command[:2] == ["less", "-R"]
    assert r"\e quit" in command[-1]


def test_the_fallback_pager_leaves_the_space_past_the_end_blank():
    assert "--tilde" in popup._less_command()


def test_rich_colours_statuses_by_state():
    console = rich.console.Console(force_terminal=True, width=80)
    segments = popup._render_markdown(
        console,
        "\n\n---\n\n".join(
            [
                "**Status:** working",
                "**Status:** done - merged",
                "**Status:** blocked - need a key",
                "**Status:** (no Status line)",
            ]
        ),
    )
    styles = {segment.text: segment.style for segment in segments if segment.text.strip()}

    assert styles["working"].color.name == "yellow"
    assert styles["done - merged"].color.name == "green"
    assert styles["blocked - need a key"].color.name == "red"
    assert styles["(no Status line)"].dim


def test_the_popup_command_carries_everything_it_needs(tmp_path):
    found = target.Target(
        [tmp_path / "brief.md"],
        [tmp_path, tmp_path / "b"],
        tmp_path,
        ["Pliny", "my-session"],
        "",
        lemon=target.Identity(name="Pliny", tmux_window="2"),
    )

    cmd = popup.popup_command(found)

    assert cmd[:3] == [sys.executable, "-m", "lemonaid.cli"]
    assert cmd[3:6] == ["brief", "show", "--target"]
    assert target.from_json(json.loads(cmd[6])) == found
    assert cmd[7:] == ["--page"]


def _no_prs(ref: str, cwd: Path | None) -> str:
    return ""


def test_identity_comes_first_and_where_it_runs_comes_last(tmp_path, monkeypatch):
    monkeypatch.setattr(target.session, "session_dir", lambda _: tmp_path)
    brief = tmp_path / "task.md"
    brief.write_text("# Task\n\nStatus: working\n\n## Now\n- Building.\n")
    row = db.Notification(
        1,
        "claude:abc",
        "",
        name="popup header",
        metadata={
            "cwd": str(tmp_path),
            "tmux_session": "work",
            "tmux_window": "2",
            "git_branch": "feature/header",
            "model": "claude-opus-4-1",
        },
    )

    found = target.for_notification(row, {row.channel: brief}, "🍋")
    rendered = render.markdown(found, 1000, _no_prs)

    assert rendered.startswith("### 🍋 popup header · Claude / Opus 4.1 · work:2")
    assert " @ " not in rendered and "PR" not in rendered
    assert rendered.index("popup header") < rendered.index("Status:") < rendered.index("**Task**")
    assert rendered.index("Building.") < rendered.index("feature/header")
    assert rendered.index("feature/header") < rendered.index("task.md")


def _show_file(path: Path, capsys) -> str:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["brief", "show", "--file", str(path)])
    args.func(args)
    return capsys.readouterr().out


def test_brief_without_attached_session_says_so(tmp_path, capsys):
    brief = tmp_path / "task.md"
    brief.write_text("# Task\n\nStatus: waiting\n")

    rendered = _show_file(brief, capsys)

    assert rendered.startswith("**No attached session**")
    assert "task.md" in rendered


def test_attached_file_shows_its_session_header(tmp_path, capsys):
    brief = tmp_path / "task.md"
    brief.write_text("# Task\n\nStatus: working\n")
    with db.connect() as conn:
        row = db.add(
            conn, "claude:attached", "", metadata={"tmux_session": "work", "tmux_window": "2"}
        )
        attached.attach(conn, row.channel, brief)

    rendered = _show_file(brief, capsys)

    assert "Claude · work:2" in rendered
    assert "No attached session" not in rendered


def test_multi_lemon_briefs_each_show_their_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(target.session, "session_dir", lambda _: tmp_path)
    author = tmp_path / "author.md"
    reviewer = tmp_path / "reviewer.md"
    for path in (author, reviewer):
        path.write_text(f"# {path.stem}\n\nStatus: working\n")
    rows = [
        db.Notification(
            1,
            "codex:author",
            "",
            name="Author",
            metadata={"tmux_session": "work", "tmux_window": "2"},
        ),
        db.Notification(
            2,
            "claude:reviewer",
            "",
            name="Reviewer",
            metadata={"tmux_session": "work", "tmux_window": "4"},
        ),
    ]
    found = target.for_session("work", rows, {rows[0].channel: author, rows[1].channel: reviewer})

    rendered = render.markdown(found, 1000, _no_prs)

    assert rendered.startswith("# work · 2 lemons\n\n---\n\n### w2 · Author · Codex")
    assert rendered.index("### w2 · Author") < rendered.index("### w4 · Reviewer · Claude")
    assert rendered.index("### w4") < rendered.index("*w2 · `") < rendered.index("*w4 · `")


def test_session_without_a_recorded_lemon_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(target.session, "session_dir", lambda _: tmp_path)

    found = target.for_session("work", [], {})

    assert found.header == "**No lemon recorded in work**"


def test_home_paths_contract_only_at_the_start(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    assert display.home_path(tmp_path / "home" / "task.md") == "~/task.md"
    assert display.home_path(tmp_path / "home-other" / "task.md") == str(
        tmp_path / "home-other" / "task.md"
    )


def test_the_popup_targets_the_calling_client_not_the_lemons_session(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **_: calls.append(argv))
    monkeypatch.setattr(popup, "_client_width", lambda: 200)
    monkeypatch.setattr(popup.dismiss, "bound_sequences", lambda: ["`b"])

    popup.open_popup(
        target.Target([], [Path("/work/place")], Path("/work/place"), ["Pliny"], "#5 thing")
    )

    [argv] = calls
    assert argv[:2] == ["tmux", "display-popup"]
    assert "-t" not in argv and "-c" not in argv
    assert argv[argv.index("-T") + 1] == " ##5 thing "
    assert argv[argv.index("-w") + 1] == "140"
    assert argv[argv.index("-S") + 1] == "fg=yellow"
    assert argv[argv.index("--dismiss") + 1] == "`b"


def test_the_popup_keeps_ninety_percent_on_a_narrower_client():
    assert popup._popup_width(120) == "108"


def test_the_popup_still_has_a_bounded_width_when_tmux_cannot_answer():
    assert popup._popup_width(None) == "140"


def test_the_pager_also_quits_on_the_keys_it_is_given():
    assert popup._less_command(["`b"])[-1].endswith(r";`b quit")
