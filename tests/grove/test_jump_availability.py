import dataclasses

from lemonaid import go
from lemonaid.config import Config
from lemonaid.grove.draw import canvas, colors, lemon_list
from lemonaid.grove.source import live
from lemonaid.grove.tui import keys, select_view
from lemonaid.grove.tui.frame import render
from lemonaid.inbox.tui.rows import brief_cards

from .shared import NOW
from .test_blocks import notification, read


def test_blocked_lemon_with_reused_tty_is_drawn_with_its_jump_failure(monkeypatch):
    row = dataclasses.replace(
        notification("codex:a", "work"),
        metadata={
            "tmux_session": "work",
            "tty": "/dev/reused",
            "cwd": "/work",
            "tmux_session_order": [100, 90, 2],
            "tmux_pane_identity": ["%7", 90],
        },
    )
    inputs = dataclasses.replace(
        read([row], {}),
        cards={row.channel: brief_cards.CardBrief("blocked", "", NOW, needs="choose markup")},
    )
    monkeypatch.setattr(go, "_tmux", lambda *args: "%8|/dev/reused|stranger|200|190|$3")
    grove = live._arranged(inputs, Config())
    tree = grove.blocks[0].trees[0]
    lemon = tree.lemons[0]
    assert lemon.status == "blocked"
    assert "gone or ambiguous" in lemon.jump_problem
    assert colors.lemon_glyph(lemon) == "x"
    shown = "\n".join(line.plain for line in grove.cards[row.channel])
    assert "Cannot jump:" in shown and "choose markup" in shown
    assert all(line.cell_len <= lemon_list.WIDTH - 2 for line in grove.cards[row.channel])
    letter = grove.arrangement.trees[("", tree.key)].letter
    selected = keys.Where(
        block="0", selecting=True, selected_tree=letter, selected_lemon=row.channel
    )
    assert "no jump:" in select_view.prompt(selected, grove.blocks, grove.arrangement, "tab")
    for where in (keys.Where(block="0"), keys.Where(search="codex:a"), selected):
        text = "\n".join(canvas.plain_lines(render(grove, where, 160, 48, 0.0)))
        assert "no jump" in text
    for width in (140, 160):
        for where in (keys.Where(search="codex:a"), selected):
            picture = render(grove, where, width, 48, 0.0)
            prompt = canvas.plain_lines(picture)[-1]
            assert "Recorded tmux pane is gone or ambiguous" in prompt
    # A fresh identity becomes available on the next refresh without changing its blocked ask.
    monkeypatch.setattr(go, "_tmux", lambda *args: "%7|/dev/reused|renamed|100|90|$2")
    refreshed = live._arranged(inputs, Config())
    assert not refreshed.blocks[0].trees[0].lemons[0].jump_problem


def test_inbox_event_loop_does_not_query_jump_targets(monkeypatch):
    def unexpected(*args):
        raise AssertionError("pane lookup on the event loop")

    monkeypatch.setattr(go, "jump_problems", unexpected)
    assert live._arranged(read([notification("claude:a", "work")], {}), Config(), cards=False)
