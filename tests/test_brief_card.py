"""A brief's identity drawn in the inbox card's colours."""

from pathlib import Path

from lemonaid.brief import render, target
from lemonaid.inbox.tui import brief_card, utils

_LEMON = target.Identity(
    name="author",
    backend="Claude",
    model="Opus 5.5",
    provider="anthropic",
    tmux_session="work",
    tmux_window="2",
    directory="~/work",
    branch="feat/x",
)


def _section(state: str, prs: tuple[tuple[str, str], ...] = ()) -> render.Section:
    return render.Section(_LEMON, "Task", state, state, prs, Path("/b.md"), 0, "")


def _styles(text, fragment: str) -> set[str]:
    start = text.plain.index(fragment)
    return {str(span.style) for span in text.spans if span.start <= start < span.end and span.style}


def test_header_has_the_cards_fields_in_the_cards_colours():
    text = brief_card.header(_section("working", (("#74", "merged"),)), False, 0, 60)
    lines = text.plain.split("\n")

    assert lines[0].startswith(f"{utils.HERE_BAR} author") and lines[0].endswith("Opus 5.5")
    assert len(lines[0]) == 60
    assert lines[1] == f"{utils.HERE_BAR} work:2 · ~/work · feat/x"
    assert lines[2] == f"{utils.HERE_BAR} working · updated just now · #74 merged"
    assert any(utils.FIELD_STYLES["name"] in s for s in _styles(text, "author"))
    assert utils.FIELD_STYLES["cwd"] in _styles(text, "~/work")
    assert utils.FIELD_STYLES["branch"] in _styles(text, "feat/x")
    assert "magenta" in _styles(text, "#74 merged")


def test_blocked_fills_the_headline_like_a_blocked_card():
    text = brief_card.header(_section("blocked"), True, 0, 40)

    assert any(utils.ATTENTION_COLOR in s for s in _styles(text, "author"))
    assert text.plain.split("\n")[1].startswith(f"{utils.HERE_BAR} w2 · ")


def test_the_session_bar_spans_the_width():
    assert brief_card.session_bar("# work · 2 lemons", 30).plain == "work · 2 lemons".center(30)
