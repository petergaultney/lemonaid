from lemonaid.grove.tui.keys import matches

from ..shared import block, lemon, tree


def test_brief_id_matches_come_before_session_and_name_matches():
    blocks = (
        block("a", "1", tree("pizza-oven", lemon("claude:oven"))),
        block("b", "2", tree("tars/limits", lemon("claude:jam", "PizzaJam"))),
    )
    assert [m.lemon.channel for m in matches(blocks, "pizza")] == ["claude:jam", "claude:oven"]


def test_blank_text_matches_nothing():
    assert matches((block("a", "1", tree("x")),), "  ") == []
