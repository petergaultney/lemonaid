"""Bare paths and URLs in a brief become short links that survive wrapping."""

import asyncio
import re
from pathlib import Path

import pytest
import rich.console
import rich.markdown
from textual.app import App, ComposeResult
from textual.widgets._markdown import MarkdownH2, MarkdownParagraph, MarkdownTableCellContents

from lemonaid.brief import links
from lemonaid.inbox.tui import brief_view

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
