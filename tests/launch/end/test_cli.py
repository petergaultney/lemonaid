"""`lemon end` passes on the Statuses its caller expects, and records who ended it."""

import argparse

import pytest

from lemonaid.brief import lemon
from lemonaid.launch.end import cli, plan


@pytest.fixture
def builds(monkeypatch) -> list[tuple]:
    calls: list[tuple] = []

    def build(conn, target, config, expected, by):
        calls.append((target, expected, by))
        return {}

    monkeypatch.setattr(plan, "build", build)
    return calls


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers())
    return parser.parse_args(["end", "Bit.review", *argv])


def test_it_expects_done_unless_told_otherwise(builds, monkeypatch):
    monkeypatch.setattr(lemon, "own_id", lambda conn, channel: "Author.work")

    cli._planned(_parse())
    cli._planned(_parse("--expect", "approve", "--expect", "none"))

    assert builds == [
        ("Bit.review", ["done"], "Author.work"),
        ("Bit.review", ["approve", "none"], "Author.work"),
    ]


def test_a_person_at_a_shell_ends_it_as_the_user(builds, monkeypatch):
    def unattached(conn, channel):
        raise LookupError("No brief attached to 'tmux:%1', so it has no Lemon-ID")

    monkeypatch.setattr(lemon, "own_id", unattached)

    cli._planned(_parse())

    assert builds == [("Bit.review", ["done"], "user")]


def test_ending_a_lemon_alone_in_its_session_points_at_place_toss(capsys):
    planned = {
        "lemon_id": "Bit.work",
        "source": None,
        "card": True,
        "waiters": [],
        "archived": False,
        "brief": "/b/work.md",
        "closing": "leave its pane as it is: its harness has already exited",
        "sole_session": "work/feat",
    }

    cli._print({"phase": "dry-run", "plan": planned}, False)
    cli._print({"phase": "ended", "plan": planned, "done": []}, False)

    out = capsys.readouterr().out
    assert "It is the only lemon in tmux session 'work/feat': `lemonaid place toss`" in out
    assert "It was the only lemon in tmux session 'work/feat'" in out
