"""The popup: where it opens, and that its command stands on its own."""

import subprocess
import sys
from pathlib import Path

from lemonaid.brief import popup


def test_the_fallback_pager_quits_on_escape_as_well_as_q():
    command = popup._less_command()

    assert command[:2] == ["less", "-R"]
    assert r"\e quit" in command[2]


def test_the_popup_command_carries_everything_it_needs(tmp_path):
    cmd = popup.popup_command(tmp_path, ["Pliny", "my-session"])

    assert cmd[:3] == [sys.executable, "-m", "lemonaid.cli"]
    assert cmd[3:] == [
        "brief",
        "show",
        "--dir",
        str(tmp_path),
        "--name",
        "Pliny",
        "--name",
        "my-session",
        "--page",
    ]


def test_the_popup_targets_the_calling_client_not_the_lemons_session(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **_: calls.append(argv))
    monkeypatch.setattr(popup, "_client_width", lambda: 200)

    popup.open_popup(Path("/work/place"), ["Pliny"], title="#5 thing")

    [argv] = calls
    assert argv[:2] == ["tmux", "display-popup"]
    assert "-t" not in argv and "-c" not in argv
    assert argv[argv.index("-T") + 1] == " ##5 thing "
    assert argv[argv.index("-w") + 1] == "140"
    assert argv[argv.index("-S") + 1] == "fg=yellow"


def test_the_popup_keeps_ninety_percent_on_a_narrower_client():
    assert popup._popup_width(120) == "108"


def test_the_popup_still_has_a_bounded_width_when_tmux_cannot_answer():
    assert popup._popup_width(None) == "140"
