import dataclasses

from lemonaid.config import Config
from lemonaid.grove.draw import card
from lemonaid.grove.source import lemon_cards, live
from lemonaid.inbox.tui.rows import brief_cards, pr_numbers

from .test_blocks import notification, read

NOW = 1_800_000_000.0


def test_a_lemons_card_carries_what_its_inbox_card_does():
    n = dataclasses.replace(
        notification("claude:a", "core"),
        name="Lemon grove map",
        message="Verified in 3e63f38c; F1 is closed.",
        created_at=NOW - 120,
        metadata={"tmux_session": "core", "cwd": "/work/lemonaid", "git_branch": "grove-select"},
    )
    inputs = dataclasses.replace(
        read([n], {}, numbers={"claude:a": (pr_numbers.PR("411"),)}),
        cards={"claude:a": brief_cards.CardBrief("blocked", "", NOW, needs="pick a layout")},
        lemon_ids={"claude:a": "FilmyBoy.spatial-lemon-jump"},
    )
    lines = lemon_cards.by_channel(inputs, Config(), card.INNER + 1, NOW)["claude:a"]
    shown = "\n".join(line.plain for line in lines)
    for part in ("Lemon grove map", "FilmyBoy", "#411", "grove-select", "Needs: pick a layout"):
        assert part in shown, part
    assert "Verified in 3e63f38c" in shown
    assert all(line.cell_len <= card.INNER for line in lines)
    assert lines[-1].plain.strip()  # without the blank line that ends an inbox card


def test_a_grove_made_on_the_inbox_event_loop_has_no_cards():
    inputs = read([notification("claude:a", "core")], {})
    assert live._arranged(inputs, Config(), cards=False).cards == {}
    assert set(live._arranged(inputs, Config()).cards) == {"claude:a"}
