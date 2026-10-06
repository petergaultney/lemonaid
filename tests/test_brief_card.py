"""A brief's identity drawn in the inbox card's colours."""

import dataclasses
from pathlib import Path

from lemonaid.brief import render, target
from lemonaid.inbox.tui import brief_card, brief_cards, utils

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
    assert lines[1] == f"{utils.HERE_BAR} work:2 · feat/x · ~/work"
    assert lines[2:5] == [f"{utils.HERE_BAR} ", f"{utils.HERE_BAR} Task", f"{utils.HERE_BAR} "]
    assert lines[5] == f"{utils.HERE_BAR} working · updated just now · #74 merged"
    assert any(utils.FIELD_STYLES["name"] in s for s in _styles(text, "author"))
    assert utils.FIELD_STYLES["cwd"] in _styles(text, "~/work")
    assert utils.FIELD_STYLES["branch"] in _styles(text, "feat/x")
    assert "magenta" in _styles(text, "#74 merged")


def test_the_project_leads_the_card_above_the_name():
    section = dataclasses.replace(_section("blocked"), project="ds-monorepo: apps/web")
    text = brief_card.header(section, False, 0, 60)
    lines = text.plain.split("\n")

    assert lines[0] == f"{utils.HERE_BAR} ds-monorepo: apps/web"
    assert lines[1].startswith(f"{utils.HERE_BAR} author")
    assert len(lines) == 7
    assert utils.ATTENTION_COLOR not in " ".join(_styles(text, "ds-monorepo"))


def test_the_task_lemon_id_and_parent_come_before_the_status():
    section = dataclasses.replace(
        _section("blocked"),
        title="Manage the plan (briefs, messaging)",
        lemon_id="plan-manager.BlessBar",
        parent="control-center.LemonAce",
        parent_name="Real HQ",
    )
    lines = brief_card.header(section, False, 0, 60).plain.split("\n")

    assert lines[2:] == [
        f"{utils.HERE_BAR} ",
        f"{utils.HERE_BAR} Manage the plan (briefs, messaging)",
        f"{utils.HERE_BAR} Brief-ID: plan-manager.BlessBar",
        f"{utils.HERE_BAR} Parent: Real HQ (control-center.LemonAce)",
        f"{utils.HERE_BAR} ",
        f"{utils.HERE_BAR} blocked · updated just now",
    ]


def test_a_compact_card_wraps_its_lemon_id_and_parent_on_one_line_rather_than_cutting_it():
    section = dataclasses.replace(
        _section("waiting"),
        lemon_id="review-lemonaid-184.PauseOld",
        parent="lemon-ids.EqualRib",
        compact=True,
    )
    lines = brief_card.header(section, True, 0, 40).plain.split("\n")

    assert " ".join(line.removeprefix(f"{utils.HERE_BAR} ").strip() for line in lines[3:-1]) == (
        "Brief-ID: review-lemonaid-184.PauseOld · Parent: lemon-ids.EqualRib"
    )
    assert all(len(line) <= 40 for line in lines)


def test_blocked_fills_the_headline_like_a_blocked_card():
    text = brief_card.header(_section("blocked"), True, 0, 40)

    assert any(utils.ATTENTION_COLOR in s for s in _styles(text, "author"))
    assert text.plain.split("\n")[1].startswith(f"{utils.HERE_BAR} w2 · ")


def test_the_session_bar_spans_the_width():
    assert brief_card.session_bar("# work · 2 lemons", 30).plain == "work · 2 lemons".center(30)


def test_merge_and_alert_fill_the_headline_green_and_red():
    assert any(
        brief_cards.MERGE_COLOR in s
        for s in _styles(brief_card.header(_section("merge"), True, 0, 40), "author")
    )
    assert any(
        brief_cards.ALERT_COLOR in s
        for s in _styles(brief_card.header(_section("alert"), True, 0, 40), "author")
    )


def test_review_fills_the_headline_brown():
    assert any(
        brief_cards.REVIEW_COLOR in s
        for s in _styles(brief_card.header(_section("review"), True, 0, 40), "author")
    )


def test_approve_fills_the_headline_purple():
    assert any(
        brief_cards.APPROVE_COLOR in s
        for s in _styles(brief_card.header(_section("approve"), True, 0, 40), "author")
    )


def test_running_fills_the_headline_teal():
    assert any(
        brief_cards.RUNNING_COLOR in s
        for s in _styles(brief_card.header(_section("running"), True, 0, 40), "author")
    )
