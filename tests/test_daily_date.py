"""A lemon hears the local date and time on its first turn of each day."""

import datetime as dt
import json
import re
from contextlib import contextmanager
from unittest.mock import patch

from lemonaid import config, daily_date
from lemonaid.claude import notify

_LINE = re.compile(r"It's \d{1,2}:\d\d[ap]m [A-Z][a-z]+day, \d{4}-\d\d-\d\d\.")


_SIX = dt.time(6, 0)


def test_the_line_is_due_once_a_day(tmp_path):
    seen = tmp_path / "seen"
    morning = dt.datetime(2026, 10, 1, 9, 14)

    assert daily_date.due(seen, morning, _SIX) == "It's 9:14am Thursday, 2026-10-01."
    daily_date.mark(seen, morning, _SIX)
    assert daily_date.due(seen, morning.replace(hour=23, minute=59), _SIX) == ""
    assert daily_date.due(seen, dt.datetime(2026, 10, 2, 12, 0), _SIX) == (
        "It's 12:00pm Friday, 2026-10-02."
    )


def test_the_day_starts_at_day_starts_not_midnight(tmp_path):
    seen = tmp_path / "seen"
    daily_date.mark(seen, dt.datetime(2026, 10, 1, 9, 14), _SIX)

    assert daily_date.due(seen, dt.datetime(2026, 10, 2, 0, 5), _SIX) == ""
    assert daily_date.due(seen, dt.datetime(2026, 10, 2, 5, 59), _SIX) == ""
    assert daily_date.due(seen, dt.datetime(2026, 10, 2, 6, 0), _SIX) == (
        "It's 6:00am Friday, 2026-10-02."
    )
    assert daily_date.due(seen, dt.datetime(2026, 10, 2, 6, 0, 10), dt.time(6, 0, 30)) == ""
    assert daily_date.due(seen, dt.datetime(2026, 10, 2, 0, 5), dt.time(0, 0)) == (
        "It's 12:05am Friday, 2026-10-02."
    )


def test_day_starts_is_configurable(tmp_path):
    for raw, expected in (
        ("", dt.time(6, 0)),
        ('day_starts = "07:30"', dt.time(7, 30)),
        ("day_starts = 05:00:00", dt.time(5, 0)),
        ('day_starts = "soon"', dt.time(6, 0)),
    ):
        path = tmp_path / "config.toml"
        path.write_text(f"[inbox]\n{raw}\n")
        assert config.load_config(path).inbox.day_starts == expected


@contextmanager
def _fake_connect():
    yield object()


def _submit(capsys) -> str:
    with (
        patch("lemonaid.claude.notify.db.connect", _fake_connect),
        patch("lemonaid.claude.notify.db.register_working"),
        patch("lemonaid.claude.notify.handoff_transfer.reclaim"),
        patch(
            "lemonaid.claude.notify.resolve_session_name",
            return_value=notify.SessionName("s", notify.TITLE_SOURCE),
        ),
        patch("lemonaid.claude.notify.get_tmux_session_name", return_value=None),
        patch("lemonaid.claude.notify.get_tty", return_value=None),
        patch("lemonaid.claude.notify.get_git_branch", return_value=None),
    ):
        notify.handle_submit('{"session_id":"abc123","cwd":"/tmp/project"}')
    out = capsys.readouterr().out
    if not out:
        return ""

    output = json.loads(out)["hookSpecificOutput"]
    assert output["hookEventName"] == "UserPromptSubmit"
    return output["additionalContext"]


def test_a_claude_session_hears_the_date_on_its_first_turn_of_the_day(capsys):
    assert _LINE.fullmatch(_submit(capsys))
    assert _submit(capsys) == ""

    daily_date.seen_path("claude:abc123").write_text("2000-01-01")

    assert _LINE.fullmatch(_submit(capsys))
