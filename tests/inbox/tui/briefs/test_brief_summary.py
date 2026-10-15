"""Results summaries appear in the brief widgets opened from the inbox."""

import asyncio

import pytest
from textual.widgets._markdown import MarkdownH2, MarkdownParagraph

from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.briefs.brief_view import BriefView

from ..shared import lemons, until


@pytest.mark.parametrize("summary", ["", "The notification now arrives."])
def test_b_shows_results_before_needs_and_refreshes_them(monkeypatch, tmp_path, summary):
    _, state = lemons(monkeypatch, tmp_path, 1)
    path = state["targets"][0].attached[0]
    source = (
        "# Work\n\nStatus: merge\n\n## Now\n\n### Needs Sam\n\n"
        "- Merge the fix.\n\n## Goal\n\nDeliver notifications.\n\n"
        "## Executive Summary of Results\n\n{summary}\n\n"
        "## Context\n\nKeep the existing delivery service.\n"
    )
    path.write_text(source.format(summary=summary))

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(60, 40)) as pilot:
            await pilot.press("b")
            await until(pilot, lambda: app._brief_target is not None)
            await pilot.pause()
            view = app.query_one(BriefView)
            headings = [h._content.plain for h in view.query(MarkdownH2)]
            assert ("Executive Summary of Results" in headings) == bool(summary)
            if summary:
                paragraphs = [p._content.plain for p in view.query(MarkdownParagraph)]
                assert paragraphs.index(summary) < paragraphs.index("Needs Sam:")
                paragraph = next(
                    p for p in view.query(MarkdownParagraph) if p._content.plain == summary
                )
                assert 0 <= paragraph.region.y < app.size.height

            path.write_text(source.format(summary="Delivery is verified."))
            app._refresh_notifications()
            await pilot.pause()
            paragraphs = [p._content.plain for p in view.query(MarkdownParagraph)]
            assert "Delivery is verified." in paragraphs
            assert not summary or summary not in paragraphs

    asyncio.run(check())
