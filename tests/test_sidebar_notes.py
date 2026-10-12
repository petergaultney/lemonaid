"""`[tui] notes`: a Markdown file kept in view under the cards."""

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Markdown

from lemonaid import keys
from lemonaid.config import KeybindingsConfig, _parse_config
from lemonaid.inbox import db
from lemonaid.inbox.tui import app, bindings
from lemonaid.inbox.tui.notes import NotesPanel

_SIDEBAR = (45, 40)  # narrow enough for cards
_STRIP = (245, 16)  # wide and short: columns


@pytest.fixture
def notes(tmp_path: Path) -> Path:
    """A notes file, named by the config every test here loads."""
    path = tmp_path / "notes.md"
    path.write_text("- `c` new window\n")
    # No timer ticks: a redraw a test sees is one the code under test asked for.
    (tmp_path / "config.toml").write_text(f'[tui]\nnotes = "{path}"\nrefresh_interval = 600\n')
    return path


def _add_session(message: str = "working") -> None:
    with db.connect() as conn:
        db.add(
            conn,
            "claude:notes-test",
            message,
            "work",
            {"cwd": "/tmp", "tty": "/dev/test"},
            switch_source="tmux",
        )


def _run(size: tuple[int, int], check, *keys_pressed: str):
    """Run *check* on a fresh inbox of *size*, after pressing *keys_pressed*."""

    async def run():
        tui = app.LemonaidApp()
        async with tui.run_test(size=size) as pilot:
            await pilot.pause()
            for key in keys_pressed:
                await pilot.press(key)
                await pilot.pause()
            return check(tui)

    return asyncio.run(run())


def _shown(tui: app.LemonaidApp) -> str | None:
    """The notes' Markdown while the panel is displayed, else None."""
    panels = tui.query(NotesPanel)
    if not panels or not panels.first().display:
        return None
    return panels.first().query_one(Markdown).source


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, None, id="unset"),
        pytest.param("", None, id="empty"),
        pytest.param(3, None, id="not-a-path"),
        pytest.param("~/notes.md", Path("~/notes.md").expanduser(), id="home-expanded"),
    ],
)
def test_the_notes_setting_is_a_path_or_nothing(raw, expected):
    data = {"tui": {} if raw is None else {"notes": raw}}

    assert _parse_config(data).tui.notes == expected


def test_a_sidebar_shows_the_notes(notes):
    assert _run(_SIDEBAR, _shown) == "- `c` new window\n"


def test_the_notes_key_hides_them_and_brings_them_back(notes):
    assert _run(_SIDEBAR, _shown, "N") is None
    assert _run(_SIDEBAR, _shown, "N", "N") == "- `c` new window\n"


def test_a_top_strip_leaves_them_out(notes):
    """A strip of columns, a few rows high, has no room to give."""
    assert _run(_STRIP, _shown) is None


def test_without_the_setting_there_is_no_panel():
    assert _run(_SIDEBAR, lambda tui: len(tui.query(NotesPanel))) == 0


def test_an_edit_shows_without_a_restart(notes):
    def edit_then_look(tui: app.LemonaidApp) -> str | None:
        notes.write_text("- `w` pick a window, from a longer line\n")
        tui._refresh_notes()
        return _shown(tui)

    assert _run(_SIDEBAR, edit_then_look) == "- `w` pick a window, from a longer line\n"


def test_a_missing_file_says_so(notes):
    notes.unlink()

    assert f"No notes at `{notes}`" in _run(_SIDEBAR, _shown)


def test_the_cards_give_up_the_rows_the_notes_take(notes):
    """Otherwise a card sized for the whole pane pushes the list into scrolling."""
    notes.write_text("\n\n".join(f"line {i}" for i in range(8)))
    _add_session(" ".join(f"word{i}" for i in range(300)))

    def lines(tui: app.LemonaidApp) -> int:
        return tui._card_shape()[1]

    assert _run(_SIDEBAR, lines) < _run(_SIDEBAR, lines, "N")


def test_the_notes_key_is_checked_for_conflicts():
    assert any("notes" in warning for warning in keys.conflicts(KeybindingsConfig(notes="a")))


def _drawn_heights(tui: app.LemonaidApp) -> list[int]:
    return [row.height for row in tui.query_one("#main_table", app.DataTable).rows.values()]


def test_the_first_paint_already_leaves_room_for_the_notes(notes):
    """The panel's height is known only after its first layout; the cards follow it then."""
    notes.write_text("\n\n".join(f"line {i}" for i in range(8)))
    _add_session(" ".join(f"word{i}" for i in range(300)))

    def first_then_refreshed(tui: app.LemonaidApp) -> tuple[list[int], list[int]]:
        first = _drawn_heights(tui)
        tui._refresh_notifications()
        return first, _drawn_heights(tui)

    first, refreshed = _run(_SIDEBAR, first_then_refreshed)
    assert first == refreshed


def test_hiding_the_notes_gives_the_cards_their_rows_at_once(notes):
    notes.write_text("\n\n".join(f"line {i}" for i in range(8)))
    _add_session(" ".join(f"word{i}" for i in range(300)))

    (with_notes,) = _run(_SIDEBAR, _drawn_heights)
    (without,) = _run(_SIDEBAR, _drawn_heights, "N")
    assert with_notes < without


@pytest.mark.parametrize("how", ["click", "shift+tab"])
def test_the_notes_never_take_the_keys_from_the_list(notes, how):
    """Focused notes would scroll on the arrow keys, and the list would stop moving."""
    notes.write_text("\n\n".join(f"line {i}" for i in range(40)))

    async def run():
        tui = app.LemonaidApp()
        async with tui.run_test(size=_SIDEBAR) as pilot:
            await pilot.pause()
            if how == "click":
                await pilot.click(NotesPanel)
            else:
                await pilot.press(how)
            await pilot.pause()
            return tui.focused.id if tui.focused else None

    assert asyncio.run(run()) == "main_table"


def test_an_unchanged_file_is_not_rendered_again(notes):
    """A refresh tick comes three times a second."""

    def refresh_twice(tui: app.LemonaidApp) -> int:
        markdown = tui.query_one(NotesPanel).query_one(Markdown)
        renders = []
        render = markdown.update
        markdown.update = lambda text: (renders.append(text), render(text))[1]
        tui._refresh_notes()
        tui._refresh_notes()
        return len(renders)

    assert _run(_SIDEBAR, refresh_twice) == 0


@pytest.mark.parametrize(
    ("configured", "bound"),
    [pytest.param(True, True, id="with-notes"), pytest.param(False, False, id="without")],
)
def test_the_notes_key_is_bound_and_listed_only_with_notes(tmp_path, configured, bound):
    if configured:
        (tmp_path / "config.toml").write_text(f'[tui]\nnotes = "{tmp_path / "n.md"}"\n')
    tui = app.LemonaidApp()

    assert ("N" in tui._bindings.key_to_bindings) is bound
    assert (bindings.help_keys(tui.config).notes == "N") is bound
