"""Bare paths and URLs in a brief become short links that survive wrapping."""

import asyncio
import re
from pathlib import Path

import pytest
import rich.console
import rich.markdown
from textual.app import App, ComposeResult
from textual.geometry import Region
from textual.widgets._markdown import MarkdownH2, MarkdownParagraph, MarkdownTableCellContents

from lemonaid.brief import doc_table, links
from lemonaid.inbox.tui.briefs import brief_view

_VAULTS = (Path.home() / "work/vault", Path.home() / "trove")
_LONG = "https://example.com/" + "/".join(f"segment-{i}" for i in range(12)) + "/end?x=1&y=2"
_OSC8 = re.compile(r"\x1b\]8;[^;]*;(?P<url>[^\x1b]*)\x1b\\(?P<text>.*?)\x1b\]8;;\x1b\\", re.DOTALL)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "see ~/trove/94 System Lemons/plan-2026-09.md.",
            "see [plan-2026-09](<obsidian://open?vault=trove&file=94%20System%20Lemons%2Fplan-2026-09>).",
        ),
        (
            "~/work/vault/pr-reviews/74-thing.md",
            "[74-thing](<obsidian://open?vault=vault&file=pr-reviews%2F74-thing>)",
        ),
        (
            "(https://github.com/o/lemonaid/pull/74), then",
            "([lemonaid#74](<https://github.com/o/lemonaid/pull/74>)), then",
        ),
        (
            "https://en.wikipedia.org/wiki/Foo_(bar)!",
            "[en.wikipedia.org/…/Foo_(bar)](<https://en.wikipedia.org/wiki/Foo_(bar)>)!",
        ),
        (
            "obsidian://open?vault=vault&file=inbox%2Fnote-1;",
            "[note-1](<obsidian://open?vault=vault&file=inbox%2Fnote-1>);",
        ),
        ("https://example.com/a.", "[example.com/a](<https://example.com/a>)."),
    ],
)
def test_bare_paths_and_urls_get_short_labels(source, expected):
    assert links.linkify(source, _VAULTS) == expected


def test_a_long_url_gets_a_short_label_and_keeps_its_whole_target():
    linked = links.linkify(f"- Waiting on: {_LONG}", _VAULTS)

    assert linked == f"- Waiting on: [example.com/…/end](<{_LONG}>)"


@pytest.mark.parametrize(
    "source",
    [
        "[the plan](https://example.com/plan) and <https://example.com/auto>",
        "`~/trove/a.md` and ``https://example.com/code``",
        "```\nhttps://example.com/fenced\n~/trove/a.md\n```",
        "![img](https://example.com/i.png)",
        "~/trove/a.md.bak and ~/other/a.md and http:/not-a-url",
    ],
)
def test_existing_links_code_and_near_misses_are_left_alone(source):
    assert links.linkify(source, _VAULTS) == source


def test_a_full_path_under_a_vault_root_links_like_its_tilde_form():
    assert links.linkify(f"{Path.home()}/trove/notes/a b.md", _VAULTS) == (
        "[a b](<obsidian://open?vault=trove&file=notes%2Fa%20b>)"
    )


def test_without_configured_vaults_paths_stay_as_written_and_urls_still_link():
    assert links.linkify("~/trove/a.md and https://example.com/a", ()) == (
        "~/trove/a.md and [example.com/a](<https://example.com/a>)"
    )


def test_a_root_nested_in_another_links_to_its_own_vault():
    vaults = (Path.home() / "notes", Path.home() / "notes/inner")

    assert links.linkify("~/notes/inner/x.md ~/notes/y.md", vaults) == (
        "[x](<obsidian://open?vault=inner&file=x>) [y](<obsidian://open?vault=notes&file=y>)"
    )


def test_brackets_in_a_label_are_escaped():
    assert links.linkify("obsidian://open?vault=trove&file=%5Bdraft%5D%20x", _VAULTS) == (
        r"[\[draft\] x](<obsidian://open?vault=trove&file=%5Bdraft%5D%20x>)"
    )


def _hyperlinks(ansi: str) -> list[tuple[str, str]]:
    return [(m["url"], re.sub(r"\x1b\[[0-9;]*m", "", m["text"])) for m in _OSC8.finditer(ansi)]


def test_rich_wraps_a_label_with_the_link_on_every_line():
    console = rich.console.Console(force_terminal=True, width=12, color_system="truecolor")
    with console.capture() as capture:
        console.print(rich.markdown.Markdown(links.linkify(f"x {_LONG}", _VAULTS)))

    found = _hyperlinks(capture.get())

    assert len(found) >= 2  # the label wrapped
    assert {url for url, _ in found} == {_LONG}
    assert "".join(text for _, text in found).replace(" ", "") == "example.com/…/end"


def test_the_sidebar_adds_a_terminal_hyperlink_to_each_markdown_link():
    class _Show(App):
        def compose(self) -> ComposeResult:
            yield brief_view._Markdown(
                links.linkify(f"Waiting on {_LONG} and [kept](https://k.example/)", _VAULTS)
            )

    async def check() -> list[str]:
        app = _Show()
        async with app.run_test(size=(20, 10)) as pilot:
            await pilot.pause()
            paragraph = app.query_one(MarkdownParagraph)
            return [
                span.style.link
                for span in paragraph._content.spans
                if getattr(span.style, "link", None)
            ]

    assert asyncio.run(check()) == [_LONG, "https://k.example/"]


def test_a_click_in_the_sidebar_opens_each_link_as_written(monkeypatch):
    opened: list[list[str]] = []
    monkeypatch.setattr(brief_view.subprocess, "Popen", lambda argv, **_: opened.append(argv))
    source = (
        "- first [PR #74](https://github.com/o/r/pull/74) here\n"
        "- then ~/trove/94 System Lemons/pr-reviews/lemonaid-74.md there\n"
    )

    class _Show(App):
        def compose(self) -> ComposeResult:
            yield brief_view._Markdown(links.linkify(source, _VAULTS))

    async def check() -> None:
        app = _Show()
        async with app.run_test(size=(80, 10)) as pilot:
            await pilot.pause()
            for paragraph in app.query(MarkdownParagraph):
                text = paragraph._content.plain
                label = "PR #74" if "PR #74" in text else "lemonaid-74"
                await pilot.click(paragraph, offset=(text.index(label) + 1, 0))
                await pilot.pause()

    asyncio.run(check())

    assert [argv[-1] for argv in opened] == [
        "https://github.com/o/r/pull/74",
        "obsidian://open?vault=trove&file=94%20System%20Lemons%2Fpr-reviews%2Flemonaid-74",
    ]


def test_a_click_on_a_table_cell_link_opens_it_as_written(monkeypatch):
    opened: list[list[str]] = []
    browsed: list[str] = []
    monkeypatch.setattr(brief_view.subprocess, "Popen", lambda argv, **_: opened.append(argv))
    review = "obsidian://open?vault=trove&file=94%20System%20Lemons%2Fpr-reviews%2Flemonaid-81"
    source = (
        "| Work | PR | Review |\n|---|---|---|\n"
        f"| delivery | [lemonaid#81](https://github.com/o/r/pull/81) | [review doc]({review}) |\n"
    )

    class _Show(App):
        def compose(self) -> ComposeResult:
            yield brief_view._Markdown(links.linkify(source, _VAULTS))

        def open_url(self, url: str, *, new_tab: bool = True) -> None:
            browsed.append(url)

    async def check() -> list[str]:
        app = _Show()
        async with app.run_test(size=(80, 10)) as pilot:
            await pilot.pause()
            cell = next(
                c for c in app.query(MarkdownTableCellContents) if "review" in str(c.content)
            )
            await pilot.click(cell, offset=(2, 0))
            await pilot.pause()
            return [s.style.link for s in cell.content.spans if getattr(s.style, "link", None)]

    assert asyncio.run(check()) == [review]
    assert browsed == []
    assert [argv[-1] for argv in opened] == [review]


def test_a_heading_link_is_a_terminal_hyperlink_and_opens_as_written(monkeypatch):
    opened: list[list[str]] = []
    monkeypatch.setattr(brief_view.subprocess, "Popen", lambda argv, **_: opened.append(argv))
    review = "obsidian://open?vault=trove&file=94%20System%20Lemons%2Fpr-reviews%2Flemonaid-81"

    class _Show(App):
        def compose(self) -> ComposeResult:
            yield brief_view._Markdown(f"## see the [review doc]({review})")

    async def check() -> list[str]:
        app = _Show()
        async with app.run_test(size=(80, 10)) as pilot:
            await pilot.pause()
            heading = app.query_one(MarkdownH2)
            await pilot.click(heading, offset=(heading._content.plain.index("review") + 1, 0))
            await pilot.pause()
            return [s.style.link for s in heading._content.spans if getattr(s.style, "link", None)]

    assert asyncio.run(check()) == [review]
    assert [argv[-1] for argv in opened] == [review]


@pytest.mark.parametrize("backticks", [False, True])
def test_document_path_cells_link_to_vault_or_file_urls(tmp_path, backticks):
    vault = tmp_path / "notes"
    paths = [vault / "a doc.md", tmp_path / "other [draft].html"]
    for path in paths:
        cell = f"`{path}`" if backticks else str(path)
        source = f"### Docs\n\n| Document | Purpose | Watch |\n|---|---|---|\n| {cell} | Design | All edits |\n"
        linked = links.linkify(source, [vault])
        target = "obsidian://open?vault=notes&file=a%20doc" if path == paths[0] else path.as_uri()
        assert target in linked
        assert links.linkify(linked, [vault]) == linked


@pytest.mark.parametrize("generated", [False, True])
def test_docs_cells_are_terminal_links_and_click_the_correct_opener(
    tmp_path, monkeypatch, generated
):
    vault = tmp_path / "notes"
    paths = [vault / "a doc.md", tmp_path / "outside file.html"]
    targets = ["obsidian://open?vault=notes&file=a%20doc", paths[1].as_uri()]
    if generated:
        source = "\n".join(
            doc_table.render([doc_table.Row(path, "Review") for path in paths], [vault])
        )
    else:
        source = "| Document | Purpose | Watch |\n|---|---|---|\n" + "\n".join(
            f"| `{path}` | Review | Relay comments |" for path in paths
        )
    opened = []
    monkeypatch.setattr(
        brief_view.subprocess, "Popen", lambda argv, **kwargs: opened.append(argv[-1])
    )

    class Show(App):
        def compose(self):
            yield brief_view._Markdown(links.linkify(source, [vault]))

    async def check():
        app = Show()
        async with app.run_test(size=(240, 12)) as pilot:
            await pilot.pause()
            found = []
            for cell in app.query(MarkdownTableCellContents):
                urls = [
                    span.style.link
                    for span in cell.content.spans
                    if getattr(span.style, "link", None)
                ]
                if urls:
                    found.extend(urls)
                    await pilot.click(cell, offset=(2, 0))
                    await pilot.pause()
            return found

    assert asyncio.run(check()) == targets
    assert opened == targets


def test_long_document_path_uses_a_short_label_without_changing_its_target(tmp_path):
    path = tmp_path / ("deep/" * 12) / ("long-document-name-" * 6 + ".md")
    source = "\n".join(
        doc_table.render([doc_table.Row(path, "Explain defaults", doc_table.Watch.ALL_EDITS)])
    )
    linked = links.linkify(source, ())
    assert path.as_uri() in linked
    label = re.search(r"\[([^]]+)\]", linked)[1]
    assert len(label) <= 40 and label.endswith("…")
    assert links.linkify(linked, ()) == linked


def test_docs_table_has_readable_columns_at_sidebar_width(tmp_path):
    path = tmp_path / ("deep/" * 12) / "theory-of-operation.md"
    source = "\n".join(
        doc_table.render(
            [
                doc_table.Row(
                    path,
                    "Routing caveats, event fixes and draft review notes",
                    doc_table.Watch.ALL_EDITS,
                )
            ]
        )
    )

    class Show(App):
        def compose(self):
            yield brief_view._Markdown(links.linkify(source, ()))

    async def check():
        app = Show()
        async with app.run_test(size=(80, 20)) as pilot:
            await pilot.pause()
            cells = list(app.query(MarkdownTableCellContents))
            return {str(cell.content): cell.size.width for cell in cells}

    widths = asyncio.run(check())
    assert widths["Purpose"] >= 15
    assert widths["Watch"] >= len("All edits")
    assert max(widths.values()) < 60


@pytest.mark.parametrize("mode", list(doc_table.Watch))
def test_wrapped_document_link_clicks_on_each_line(tmp_path, monkeypatch, mode):
    path = tmp_path / ("deep/" * 12) / "Design notes for unified notifications.md"
    source = "\n".join(
        doc_table.render(
            [
                doc_table.Row(
                    path,
                    "Routing caveats and event fixes for the draft review",
                    mode,
                )
            ]
        )
    )
    opened = []
    monkeypatch.setattr(
        brief_view.subprocess, "Popen", lambda argv, **kwargs: opened.append(argv[-1])
    )

    class Show(App):
        def compose(self):
            yield brief_view._Markdown(links.linkify(source, ()))

    async def check():
        app = Show()
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            cell = next(
                cell
                for cell in app.query(MarkdownTableCellContents)
                if "Design" in str(cell.content)
            )
            assert cell.size.height > 1
            assert cell.tooltip == path.as_uri()
            await pilot.click(cell, offset=(2, 0))
            await pilot.pause()
            await pilot.click(cell, offset=(2, 1))
            await pilot.pause()
            watch = next(
                cell
                for cell in app.query(MarkdownTableCellContents)
                if str(cell.content) == mode.value
            )
            assert watch.size.width >= len(mode.value) + 2
            watch_lines = watch.render_lines(Region(0, 0, watch.size.width, watch.size.height))
            assert any(mode.value in line.text for line in watch_lines)
            lines = cell.render_lines(Region(0, 0, cell.size.width, cell.size.height))
            urls = [
                [segment.style.link for segment in line if segment.style and segment.style.link]
                for line in lines
            ]
            assert sum(bool(line) for line in urls) >= 2
            assert {url for line in urls for url in line} == {path.as_uri()}

    asyncio.run(check())
    assert opened == [path.as_uri(), path.as_uri()]
