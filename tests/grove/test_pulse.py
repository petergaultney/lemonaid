import asyncio
import dataclasses
import types

from textual import events

from lemonaid.grove.draw import canvas, colors, trees
from lemonaid.grove.tui import pulse, screen
from lemonaid.grove.tui.app import GroveApp
from lemonaid.grove.tui.frame import render
from lemonaid.grove.tui.keys import Where

from .shared import lemon, tree
from .test_frame import GROVE

WORKING = dataclasses.replace(
    GROVE,
    blocks=tuple(
        dataclasses.replace(
            b,
            trees=tuple(
                dataclasses.replace(
                    t, lemons=tuple(dataclasses.replace(lemon, working=True) for lemon in t.lemons)
                )
                for t in b.trees
            ),
        )
        for b in GROVE.blocks
    ),
)
_SIZE = (160, 48)


def _rgb(color: str) -> tuple[int, ...]:
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def test_a_frame_between_the_ends_matches_drawing_the_grove_at_that_phase():
    def draw(phase: float):
        return render(WORKING, Where(block="1"), *_SIZE, phase, {})

    ends = pulse.ends(draw)
    assert ends.changing
    blended, drawn = pulse.frame(ends, 0.5), draw(0.5)
    for x, y in ends.changing:
        a, b = _rgb(blended.rows[y][x].fg), _rgb(drawn.rows[y][x].fg)
        assert all(abs(p - q) <= 2 for p, q in zip(a, b, strict=True))


def _colors(app: GroveApp) -> list[str]:
    picture = app.screen.query_one("GroveMap").picture
    return [cell.fg for row in picture.rows for cell in row]


def test_a_working_lemon_keeps_changing_color_even_in_a_grove_shown_again(monkeypatch):
    clock = [0.0]
    # The screen's clock only: the app keeps its own.
    monkeypatch.setattr(screen, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))

    async def run() -> tuple[bool, bool, bool]:
        app = GroveApp(lambda: WORKING, 60.0, None, lambda _: "", leave=lambda: None)
        async with app.run_test(size=_SIZE) as pilot:

            async def changes() -> bool:
                seen = []
                for now in (0.0, pulse.PERIOD / 4, pulse.PERIOD / 2):
                    clock[0] = now
                    app.screen._pulse()
                    await pilot.pause()
                    seen.append(_colors(app))
                return seen[0] != seen[1] != seen[2]

            first = await changes()
            await pilot.press("escape")  # hidden, and a fresh grove waits, held
            await pilot.pause()
            clock[0] = pulse.PERIOD / 2  # the darkest, but a held grove stays at rest
            app.screen._show()
            held_at_rest = app.screen.query_one("GroveMap").picture is app.screen._ends[False].rest
            app.post_message(events.AppFocus())  # shown again
            await pilot.pause()
            return first, held_at_rest, await changes()

    first, held_at_rest, again = asyncio.run(run())
    assert first
    assert held_at_rest
    assert again


def test_working_dots_and_tags_keep_at_least_half_their_color_above_the_background():
    ground = _rgb(canvas.BACKGROUND)
    for status in ("", *colors.STATUS):
        working = dataclasses.replace(lemon("test", status=status), working=True)
        resting = dataclasses.replace(working, working=False)
        tag_colors = []
        for at in (0.0, 1.0):
            picture = canvas.blank(20, 4)
            trees.draw_tag(picture, tree("test", working), [" a working "], 0, 2, (0, 0), at)
            tag_colors.append(picture.rows[2][4].bg)
        for rest, dark in (
            (colors.lemon_color(working, 0.0), colors.lemon_color(working, 1.0)),
            tuple(tag_colors),
        ):
            full = sum(abs(a - b) for a, b in zip(_rgb(rest), ground, strict=True))
            dim = sum(abs(a - b) for a, b in zip(_rgb(dark), ground, strict=True))
            assert full > dim >= full / 2, status
        assert colors.lemon_color(resting, 0.0) == colors.lemon_color(resting, 1.0)
