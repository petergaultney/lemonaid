"""Bare paths and URLs in a brief become short links that survive wrapping."""

import asyncio
import re

import pytest
import rich.console
import rich.markdown
from textual.app import App, ComposeResult

from lemonaid.brief import links
from lemonaid.inbox.tui import brief_view

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
    assert links.linkify(source) == expected


def test_a_long_url_gets_a_short_label_and_keeps_its_whole_target():
    linked = links.linkify(f"- Waiting on: {_LONG}")

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
    assert links.linkify(source) == source


def test_brackets_in_a_label_are_escaped():
    assert links.linkify("obsidian://open?vault=trove&file=%5Bdraft%5D%20x") == (
        r"[\[draft\] x](<obsidian://open?vault=trove&file=%5Bdraft%5D%20x>)"
    )


def _hyperlinks(ansi: str) -> list[tuple[str, str]]:
    return [(m["url"], re.sub(r"\x1b\[[0-9;]*m", "", m["text"])) for m in _OSC8.finditer(ansi)]


def test_rich_wraps_a_label_with_the_link_on_every_line():
    console = rich.console.Console(force_terminal=True, width=12, color_system="truecolor")
    with console.capture() as capture:
        console.print(rich.markdown.Markdown(links.linkify(f"x {_LONG}")))

    found = _hyperlinks(capture.get())

    assert len(found) >= 2  # the label wrapped
    assert {url for url, _ in found} == {_LONG}
    assert "".join(text for _, text in found).replace(" ", "") == "example.com/…/end"


def test_the_sidebar_adds_a_terminal_hyperlink_to_each_markdown_link():
    class _Show(App):
        def compose(self) -> ComposeResult:
            yield brief_view._Markdown(
                links.linkify(f"Waiting on {_LONG} and [kept](https://k.example/)")
            )

    async def check() -> list[str]:
        app = _Show()
        async with app.run_test(size=(20, 10)) as pilot:
            await pilot.pause()
            paragraph = app.query_one(brief_view._LinkedParagraph)
            return [
                span.style.link
                for span in paragraph._content.spans
                if getattr(span.style, "link", None)
            ]

    assert asyncio.run(check()) == [_LONG, "https://k.example/"]
