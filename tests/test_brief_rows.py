"""Brief status on the top strip's one-line rows, matching the sidebar's cards."""

import asyncio

from rich.console import Console
from rich.text import Text

from lemonaid.inbox import db
from lemonaid.inbox.tui import app
from lemonaid.inbox.tui.brief_cards import CardBrief
from lemonaid.inbox.tui.utils import ATTENTION_COLOR, HERE_BAR_STYLE, jump_gutter
from lemonaid.tmux import scratch

_CONSOLE = Console(color_system="truecolor")


def _row(brief_status: str, unread: bool = False, here: bool = False) -> list[Text]:
    cells = [
        Text("12:30", style="#888888"),
        Text("●", style=f"bold {ATTENTION_COLOR}") if unread else Text(""),
        Text("Opus 5.5", style="#d88760"),
        jump_gutter(0, here) + Text("task", style="#00ffff"),
        Text("branch", style="#ff0066"),
        Text("~/work", style="#9966ff"),
        Text("message"),
        Text("ttys001"),
    ]
    return app.brief_rows.styled(
        cells,
        CardBrief(brief_status, "", 0),
        app._UNREAD_CELL,
        app._BACKEND_CELL,
        app._NAME_CELL,
        2,
    )


def _style(cell: Text, offset: int = -1):
    return cell.get_style_at_offset(_CONSOLE, offset if offset >= 0 else len(cell.plain) - 1)


def test_a_blocked_row_is_amber_with_black_text_and_a_provider_badge():
    """Deeper than the unread header's yellow, which it sits right under."""
    cells = _row("blocked", unread=True)

    assert app.brief_rows.background(CardBrief("blocked", "", 0)).bgcolor.name == "#c9a93a"
    for index in (0, 3, 4, 5, 6, 7):
        assert _style(cells[index]).color.name == "#000000"
    assert _style(cells[1]).color.name == "#000000"  # the dot, visible on yellow
    badge = _style(cells[2])
    assert (badge.color.name, badge.bgcolor.name) == ("#000000", "#d88760")


def test_a_done_row_is_blue_with_white_text_and_keeps_its_dot():
    cells = _row("done", unread=True)

    assert app.brief_rows.background(CardBrief("done", "", 0)).bgcolor.name == "#285995"
    assert _style(cells[6]).color.name == "#ffffff"
    assert _style(cells[1]).color.name == ATTENTION_COLOR


def test_the_current_session_keeps_its_green_bar():
    name = _row("blocked", here=True)[3]

    assert _style(name, 0) == _CONSOLE.get_style(HERE_BAR_STYLE)
    assert _style(name).color.name == "#000000"


def test_waiting_dims_only_once_read_and_working_is_unchanged():
    assert _style(_row("waiting")[6]).dim
    assert not _style(_row("waiting", unread=True)[6]).dim
    assert app.brief_rows.background(CardBrief("waiting", "", 0)) is None
    assert not _style(_row("working")[6]).dim
    assert _style(_row("working")[4]).color.name == "#ff0066"


def test_the_top_strip_fills_blocked_and_done_rows(monkeypatch, tmp_path):
    scratch.set_position("top")
    briefs = {}
    with db.connect() as conn:
        for index, status in enumerate(("blocked", "done", "working")):
            channel = f"claude:{status}"
            db.add(
                conn,
                channel,
                "message",
                status,
                {"cwd": str(tmp_path), "tty": f"/dev/test-{index}"},
                switch_source="tmux",
                status="read",
                created_at=1000.0 - index,
            )
            briefs[channel] = tmp_path / f"{status}.md"
            briefs[channel].write_text(f"# {status}\n\nStatus: {status}\n\n## Now\n")
    monkeypatch.setattr(
        "lemonaid.inbox.tui.app.brief.attached.for_rows",
        lambda conn, rows: {r.channel: briefs[r.channel] for r in rows if r.channel in briefs},
    )

    async def check() -> list[str]:
        tui = app.LemonaidApp(scratch_mode=True)
        tui.config.tui.brief_status = True
        async with tui.run_test(size=(140, 12)) as pilot:
            await pilot.pause()
            table = tui.query_one("#main_table", app.ClickToActTable)
            assert table.row_count == 3
            return [
                table._get_row_style(index, table.rich_style).bgcolor.name
                for index in range(table.row_count)
            ]

    # Blocked sorts first and done right below it.
    blocked, done, working = asyncio.run(check())

    assert (blocked, done) == ("#c9a93a", "#285995")
    assert working not in (blocked, done)


def test_a_merge_row_is_green_and_an_alert_row_red():
    merge = _row("merge", unread=True)
    alert = _row("alert", unread=True)

    assert app.brief_rows.background(CardBrief("merge", "", 0)).bgcolor.name == "#4fb35a"
    assert _style(merge[6]).color.name == "#000000"
    assert _style(merge[1]).color.name == "#000000"
    assert app.brief_rows.background(CardBrief("alert", "", 0)).bgcolor.name == "#c62828"
    assert _style(alert[6]).color.name == "#ffffff"
    assert _style(alert[1]).color.name == "#ffffff"
