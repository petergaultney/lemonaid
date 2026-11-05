"""Typing a block's digit shows that block alone, in full, until the key is finished or backed out."""

from lemonaid import brief, groups
from lemonaid.inbox import db

from .test_attention_mode import _brief, _keep_sessions, _run, _session, _state_dir  # noqa: F401


def _three_lemons() -> None:
    with db.connect() as conn:
        _brief(conn, _session(conn, "blocked", age=40), "blocked")
        _brief(conn, _session(conn, "review", age=30), "review")
        _session(conn, "idle", age=10)


def test_a_digit_shows_every_lemon_of_its_block_even_in_attention_mode():
    _three_lemons()

    async def steps(app, pilot):
        await pilot.press("exclamation_mark")
        await pilot.pause()
        attention = len(app._row_channels())
        await pilot.press("0")
        await pilot.pause()
        zoomed = len(app._row_channels())
        await pilot.press("backspace")
        await pilot.pause()
        return attention, zoomed, len(app._row_channels())

    assert _run(steps) == (1, 3, 1)


def test_a_typed_tree_marks_each_of_its_lemons():
    _three_lemons()

    async def steps(app, pilot):
        letter = app._content.inbox.grove.arrangement.trees[("", "/tmp")].letter
        await pilot.press("0", ".", letter)
        await pilot.pause()
        marked = set(app._content.inbox.families.roles.values())
        await pilot.press("escape")
        await pilot.pause()
        return marked, dict(app._content.inbox.families.roles)

    assert _run(steps) == ({"tree"}, {})


def test_a_lemon_in_two_groups_is_drawn_once_under_the_zoomed_one():
    with db.connect() as conn:
        shared = _session(conn, "shared", age=20)
        _brief(conn, shared, "blocked")
        lemon_id = brief.lemon.lemon_id(conn, shared)
        for name in ("alpha", "beta"):
            groups.store.add(conn, groups.store.create(conn, name), [lemon_id])

    async def steps(app, pilot):
        inbox = app._content.inbox
        digit = next(b.digit for b in inbox.grove.blocks if b.name == "alpha")
        await pilot.press(digit)
        await pilot.pause()
        return sorted(h.group.name for h in inbox.headers.values()), len(inbox.drawn) - len(
            inbox.headers
        )

    assert _run(steps) == (["alpha"], 1)
