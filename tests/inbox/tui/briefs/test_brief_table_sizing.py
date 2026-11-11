import asyncio

import pytest
from textual.app import App, ComposeResult
from textual.widgets._markdown import MarkdownTableCellContents

from lemonaid.inbox.tui.briefs import brief_view

_PRS = (
    "| Work | PR | Review |\n|---|---|---|\n"
    "| Open scratch pane on the window's brief; i for inbox "
    "| [lemonaid#531](https://github.com/petergaultney/lemonaid/pull/531) "
    "| `/Users/someone/play/lemonaid/inbox/brief-first/.z/review-531.md` |\n"
)
_DOCS = (
    "| Document | Purpose | Watch |\n|---|---|---|\n"
    "| [review-531.md](<file:///a/b/review-531.md>) | PR #531 review docket | All edits |\n"
)


def _cells(source: str, width: int) -> dict[str, tuple[int, int, str]]:
    """Each body cell's (width, height, text), keyed by column header."""

    class _Show(App):
        def compose(self) -> ComposeResult:
            yield brief_view._Markdown(source)

    async def run() -> dict[str, tuple[int, int, str]]:
        app = _Show()
        async with app.run_test(size=(width, 30)) as pilot:
            await pilot.pause()
            headers = [str(c.content) for c in app.query("MarkdownTableContent .header")]
            body = list(app.query(MarkdownTableCellContents).filter(".cell"))
            return {
                h: (c.size.width, c.size.height, str(c.content))
                for h, c in zip(headers, body, strict=True)
            }

    return asyncio.run(run())


@pytest.mark.parametrize("width", [75, 140])
def test_the_prs_table_keeps_the_link_whole_and_the_path_to_its_file_name(width):
    cells = _cells(_PRS, width)

    assert cells["PR"][2] == "lemonaid#531"
    assert cells["PR"][0] >= len("lemonaid#531")
    assert cells["Review"][2] == "review-531.md"
    assert cells["Work"][0] >= 25


def test_a_narrow_prs_table_wraps_work_at_words_not_letters():
    work_width, work_height, _ = _cells(_PRS, 75)["Work"]

    assert work_height <= 3
    assert work_width >= 25


def test_the_docs_table_gives_its_spare_width_to_the_longest_column():
    cells = _cells(_DOCS, 100)

    assert cells["Document"][0] < 20
    assert cells["Purpose"][0] > cells["Watch"][0]


_LONGER_REVIEW = (
    "| Work | PR | Review |\n|---|---|---|\n"
    "| A moderately long description of the work which must wrap "
    "| [lemonaid#535](https://example.com) | `review-535-brief-table-sizing.md` |\n"
)


_LINKED_REVIEW = _LONGER_REVIEW.replace(
    "`review-535-brief-table-sizing.md`",
    "[review-535-brief-table-sizing.md](file:///tmp/review-535-brief-table-sizing.md)",
)


@pytest.mark.parametrize(("width", "work"), [(40, 8), (50, 12), (60, 15)])
def test_a_linked_review_file_name_gives_up_width_to_work(width, work):
    cells = _cells(_LINKED_REVIEW, width)

    assert cells["PR"][2] == "lemonaid#535"
    assert cells["Work"][0] >= work


@pytest.mark.parametrize(("width", "work"), [(40, 8), (50, 15), (60, 15)])
def test_a_narrow_table_keeps_work_visible_and_the_link_whole(width, work):
    cells = _cells(_LONGER_REVIEW, width)

    assert cells["PR"][2] == "lemonaid#535"
    assert cells["PR"][0] >= len("lemonaid#535")
    assert cells["Work"][0] >= work


_SHORT_AND_LONG = (
    "| Work | Other | OK |\n|---|---|---|\n"
    "| A moderately long description of the work which must wrap "
    "| Another long description of something else that also wraps nicely | y |\n"
)


_READABLE = [
    (_LINKED_REVIEW, {"Work": 20, "Review": 14}),
    (_SHORT_AND_LONG, {"Work": 20, "Other": 20, "OK": 4}),
]


@pytest.mark.parametrize("width", [40, 60, 80, 120])
def test_no_column_with_real_text_is_squeezed_below_a_readable_width(width):
    for source, floors in _READABLE:
        cells = _cells(source, width)

        for header, floor in floors.items():
            assert cells[header][0] >= floor, (width, header, cells)


def test_a_column_of_two_characters_needs_no_more_room_than_that():
    assert _cells(_SHORT_AND_LONG, 120)["OK"][0] < 8
