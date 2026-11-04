import dataclasses
from pathlib import Path

from lemonaid.brief import render
from lemonaid.inbox import db
from lemonaid.inbox.tui.rows import brief_cards
from lemonaid.tasks.briefs import contested
from lemonaid.tasks.inspection import cases
from lemonaid.tasks.model import ledger

from ..shared import new_task


def _challenge(task: str, obligation: str, brief: str, reason: str) -> tuple[str, ...]:
    return ("challenge", task, obligation, "e1", "brief", brief, reason)


def test_only_an_open_status_claim_marks_its_briefs_status_contested():
    with db.connect() as conn:
        made = new_task(conn)
        subject = f"task:{made}"
        basis = cases.basis(conn, made)
        with ledger.transaction(conn):
            cases.apply(
                conn,
                subject,
                1,
                [
                    _challenge(subject, "status-claim", "Work.alpha", "CI failed."),
                    _challenge(subject, "check-claim", "Lead.lead", "Hand it back."),
                ],
                1.0,
                basis,
            )
        marked = contested.by_lemon(conn)
        with ledger.transaction(conn):
            cases.apply(conn, subject, 1, [("ok", subject, "fine")], 2.0, basis)
        cleared = contested.by_lemon(conn)

    assert marked == {"Work.alpha": "CI failed."}
    assert cleared == {}


def test_a_contested_card_strikes_its_status_and_says_why_unless_held_mid_turn():
    card = brief_cards.CardBrief("merge", "", 0.0, contested="CI failed.")
    held = dataclasses.replace(card, mid_turn=True, held_mid_turn=True)
    text = card.age_text(60.0)

    assert card.contested_line == "contested: CI failed."
    assert any("strike" in str(s.style) for s in text.spans if s.start == 0)
    assert card.extra_lines(age_inline=True) == 1
    assert held.contested_line == ""


def test_the_brief_popup_says_why_its_status_is_contested():
    section = render.Section(None, "Task", "merge", "merge", (), Path("/b.md"), 0, "")

    assert render.needs(section, True) == ""
    assert "**Status contested:** CI failed." in render.needs(
        dataclasses.replace(section, contested="CI failed."), True
    )
