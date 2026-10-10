"""The per-lemon facts doctor reports: listed waiters and what the pane shows."""

from lemonaid.inbox import db
from lemonaid.lemon_facts import facts
from lemonaid.messages import autoresume_tmux


def _row(**metadata) -> db.Notification:
    return db.Notification(
        id=1, channel="claude:x", message="", metadata=metadata, switch_source="tmux"
    )


def test_listed_waiters_are_the_commands_in_waiters_bullets():
    text = (
        "# t\n\n## Now\n\n- `not a waiter`\n\n## Waiters\n\n"
        "- inbox: `lemonaid inbox watch --self` (background)\n"
        "- ``lemonaid watch pr --wait 12 --me `x` ``\n"
        "Arm these after a restart.\n"
    )

    assert facts._listed_waiters(text) == [
        "lemonaid inbox watch --self",
        "lemonaid watch pr --wait 12 --me `x`",
    ]


def test_the_pane_says_whether_it_shows_an_empty_prompt(monkeypatch):
    monkeypatch.setattr(autoresume_tmux, "screen", lambda row: "output\n\u276f \n")
    assert facts._pane(_row(), True) == "empty prompt"

    monkeypatch.setattr(autoresume_tmux, "screen", lambda row: "\u276f draft\n")
    assert facts._pane(_row(), True) == "other"


def test_no_pane_is_reported_for_a_dead_harness_or_outside_tmux():
    assert facts._pane(_row(), False) is None
    assert (
        facts._pane(db.Notification(id=1, channel="c", message="", switch_source="cmux"), True)
        is None
    )
