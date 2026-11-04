"""A Needs bullet that links to a heading in a Markdown file: that section is its entry."""

import re
import urllib.parse
from collections import abc
from pathlib import Path

from lemonaid.watch import relay_comments

from . import doc_table

_FENCE = re.compile(r" {0,3}(?P<mark>`{3,}|~{3,})")
_HEADING = re.compile(r"(?P<hashes>#{1,6})\s+(?P<text>.+?)(?:\s+#+)?\s*")


def heading_of(link: str) -> str:
    """The heading a link names after `#` (the last of `#A#B`), or ""."""
    query = urllib.parse.urlparse(link) if link.startswith("obsidian://") else None
    value = urllib.parse.parse_qs(query.query).get("file", [""])[0] if query else link
    return urllib.parse.unquote(value.rpartition("#")[2]).strip() if "#" in value else ""


def _lines(text: str) -> abc.Iterator[tuple[str, re.Match[str] | None]]:
    """Each line, with its heading match; a line in a code block is never a heading."""
    fence = ""  # the opening mark of the code block we are in
    for line in text.splitlines():
        mark = _FENCE.match(line)
        if mark and not fence:
            fence = mark["mark"]
        elif mark and mark["mark"][0] == fence[0] and len(mark["mark"]) >= len(fence):
            fence = ""
        yield line, None if fence or mark else _HEADING.fullmatch(line)


def headings(text: str) -> list[str]:
    return [found["text"] for _, found in _lines(text) if found]


def section(text: str, heading: str) -> str | None:
    """The body under the first heading named *heading* (case ignored), or None when absent."""
    body: list[str] | None = None
    level = 0
    for line, found in _lines(text):
        if body is None:
            if found and found["text"].casefold() == heading.casefold():
                body, level = [], len(found["hashes"])
            continue

        if found and len(found["hashes"]) <= level:
            break

        body.append(line)

    return None if body is None else "\n".join(body).strip()


def reader(vaults: abc.Collection[Path]) -> abc.Callable[[str], str | None]:
    """A function from a Needs bullet to the section it links to, or None when it links to none."""

    def read(bullet: str) -> str | None:
        for match in doc_table.LINK.finditer(bullet):
            heading = heading_of(match["url"])
            path = doc_table.path_of(match[0], vaults)
            if not heading or not path or path.suffix != ".md":
                continue

            try:
                found = section(path.read_text(), heading)
            except OSError:
                continue

            if found is not None:
                return relay_comments.body_without_threads(found).strip()

        return None

    return read
