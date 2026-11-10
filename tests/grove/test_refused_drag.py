import asyncio
import dataclasses

from lemonaid.grove.draw import canvas, colors, plots, refusal, scene_parts
from lemonaid.grove.draw.canvas import mix
from lemonaid.grove.tui import drop, garden, keys
from lemonaid.grove.tui.app import GroveApp
from lemonaid.grove.tui.frame import render

from .test_frame import GROVE

_SIZE = (160, 48)
_BLOCK = GROVE.blocks[0]
_TREE = _BLOCK.trees[1]
_LETTER = GROVE.arrangement.trees[(_BLOCK.name, _TREE.key)].letter


def _tree_drag(onto_lead: bool) -> garden.Drag:
    drag = garden.grab(GROVE, keys.Where(block="1"), _SIZE, (10, 10), ("1", _LETTER))
    assert drag is not None
    at = GROVE.arrangement.trees[(_BLOCK.name, _TREE.key)]
    lead = GROVE.arrangement.trees[(_BLOCK.name, _BLOCK.trees[0].key)]
    return dataclasses.replace(
        drag, moved=(lead.cx - at.cx, lead.cy - at.cy) if onto_lead else (1, 0)
    )


def _changed(a: canvas.Canvas, b: canvas.Canvas) -> list[tuple[canvas.Cell, canvas.Cell]]:
    """The cells above the prompt row whose background differs between *a* and *b*."""
    return [
        (x, y)
        for row_a, row_b in zip(a.rows[:-1], b.rows[:-1], strict=True)
        for x, y in zip(row_a, row_b, strict=True)
        if x.bg != y.bg
    ]


def test_a_refused_tree_is_drawn_red_with_its_reason_in_alert():
    onto = _tree_drag(onto_lead=True)
    problem = drop.refused(GROVE, onto)
    assert problem == "another tree stands there"
    shown = drop.shown_refused(GROVE, onto)
    assert shown == refusal.Refusal(target=("1", _LETTER))

    where = keys.Where(block="1", note=drop.describe(GROVE, onto, problem))
    dragged = drop.dragged(GROVE, onto)
    plain = render(dragged, where, *_SIZE, 0.0)
    red = render(dragged, where, *_SIZE, 0.0, refused=shown)
    changed = _changed(plain, red)
    assert changed and all(cell.target == ("1", _LETTER) for cell, _ in changed)
    crown = [(a, b) for a, b in changed if "▀" <= a.char <= "▟"]  # drawn in its fg
    assert crown and all(b.fg == mix(a.fg, colors.ALERT, 0.55) for a, b in crown)
    note = canvas.plain_lines(red)[-1].index("moving tree")
    assert (plain.rows[-1][note].fg, red.rows[-1][note].fg) == (colors.WARN, colors.ALERT)


def test_a_block_dragged_onto_another_reddens_the_ground_it_would_take():
    oria, relay = GROVE.arrangement.plots["oria"], GROVE.arrangement.plots["relay"]
    digit = next(b.digit for b in GROVE.blocks if b.name == "oria")
    grabbed = garden.grab(GROVE, keys.Where(), _SIZE, (0, 0), (digit,))
    assert grabbed is not None
    drag = dataclasses.replace(grabbed, moved=(relay.x - oria.x, relay.y - oria.y))
    assert drop.refused(GROVE, drag) == "another block's ground is there"
    dragged = drop.dragged(GROVE, drag)
    shown = drop.shown_refused(GROVE, drag)
    assert shown == refusal.Refusal(plot=dragged.arrangement.plots["oria"])

    plain = render(dragged, keys.Where(), *_SIZE, 0.0)
    red = render(dragged, keys.Where(), *_SIZE, 0.0, refused=shown)
    view = scene_parts.grove_view(_SIZE, dragged.arrangement)
    tinted = {
        (col, row)
        for row, (row_a, row_b) in enumerate(zip(plain.rows, red.rows, strict=True))
        for col, (a, b) in enumerate(zip(row_a, row_b, strict=True))
        if a.bg != b.bg
    }
    drawn = {(c, r) for c, r in plots.ground_at(shown.plot, view) if 0 < r < _SIZE[1] - 1}
    assert tinted and tinted == drawn


def test_a_drag_is_red_only_while_it_would_be_refused(monkeypatch):
    refusals: list = []

    def render_(*args, **kwargs):
        refusals.append(args[11])
        return render(*args, **kwargs)

    monkeypatch.setattr("lemonaid.grove.tui.screen.render", render_)

    async def run() -> list[tuple[str, list]]:
        app = GroveApp(lambda: GROVE, 60.0, None)
        frames = []
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("1")
            await pilot.pause()
            for onto in (True, False):
                app.screen._drag, app.screen._dragged = _tree_drag(onto), True
                refusals.clear()
                app.screen._drag_frame()
                frames.append((app.screen._where.note, list(refusals)))
        return frames

    (refused_note, red), (valid_note, plain) = asyncio.run(run())
    assert "another tree stands there" in refused_note
    assert red and all(r == refusal.Refusal(target=("1", _LETTER)) for r in red)
    assert "release to drop" in valid_note
    assert plain and all(r is None for r in plain)
