"""Short clickable labels for the bare paths and URLs a worker writes in a brief.

A long URL wraps across lines, and a terminal that finds links by scanning text
loses it at the break. A Markdown link with a short label renders as one OSC 8
hyperlink per line instead, so it opens from anywhere on the label.

A `.md` path under a configured vault root, written from `~` or in full, opens
in Obsidian. Code spans, fenced blocks, autolinks and existing Markdown links are
left as written.
"""

import re
import urllib.parse
from collections import abc
from pathlib import Path

_MAX_LABEL = 40
_TRAILING = ".,;:!?'\""

_PROTECTED = (
    r"(?P<fence>^(?P<ticks>```|~~~)[^\n]*\n.*?(?:^(?P=ticks)[^\n]*$|\Z))"
    r"|(?P<code>(?P<run>`+)(?:(?!\n\n).)+?(?P=run))"
    r"|(?P<link>!?\[[^\]\n]*\]\((?:<[^>\n]*>|[^)\s]*(?:\([^)\s]*\)[^)\s]*)*)[^)\n]*\))"
    r"|(?P<autolink><[a-z][a-z0-9+.-]*:[^>\s]*>)"
)
_URL = r"(?P<url>(?<![\w/])(?:https?|obsidian)://[^\s<>`\[\]]+)"
_FLAGS = re.MULTILINE | re.DOTALL | re.IGNORECASE


def _spellings(root: Path) -> list[str]:
    """How a brief may write *root*: from `~` when it is under home, and in full."""
    home = Path.home()
    return [
        *([f"~/{root.relative_to(home).as_posix()}"] if root.is_relative_to(home) else []),
        root.as_posix(),
    ]


def _tokens(roots: abc.Iterable[Path]) -> re.Pattern[str]:
    spelled = sorted({s for root in roots for s in _spellings(root)}, key=len, reverse=True)
    if not spelled:
        return re.compile(f"{_PROTECTED}|{_URL}", _FLAGS)

    vault = (
        r"(?P<vault>(?<![\w/~])(?P<root>"
        + "|".join(re.escape(s) for s in spelled)
        + r")/(?P<rest>(?:(?!~/)[^\n`<>\[\]])*?\.md)(?![\w-]|\.\w))"
    )
    return re.compile(f"{_PROTECTED}|{vault}|{_URL}", _FLAGS)


def _trimmed(url: str) -> tuple[str, str]:
    """*url* without trailing punctuation or an unbalanced closing paren, and what was cut."""
    end = len(url)
    while end:
        unbalanced = url[end - 1] == ")" and url.count("(", 0, end) < url.count(")", 0, end)
        if url[end - 1] not in _TRAILING and not unbalanced:
            break

        end -= 1

    return url[:end], url[end:]


def _short(label: str) -> str:
    return label if len(label) <= _MAX_LABEL else f"{label[: _MAX_LABEL - 1]}…"


def _obsidian(vault: str, rest: str) -> tuple[str, str]:
    file = rest.removesuffix(".md")
    query = urllib.parse.urlencode({"vault": vault, "file": file}, quote_via=urllib.parse.quote)
    return f"obsidian://open?{query}", _short(file.rsplit("/", 1)[-1])


def _label(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "obsidian":
        file = urllib.parse.parse_qs(parsed.query).get("file", [""])[0]
        return _short(file.rsplit("/", 1)[-1] or "obsidian")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 4 and parts[2] in {"pull", "pulls", "issues"} and parts[3].isdigit():
        return f"{parts[1]}#{parts[3]}"

    return _short("/".join([parsed.netloc, *(["…"] if len(parts) > 1 else []), *parts[-1:]]))


def _link(label: str, url: str) -> str:
    escaped = re.sub(r"([\\\[\]])", r"\\\1", label)
    return f"[{escaped}](<{url}>)"


def _replace(match: re.Match[str], vaults: abc.Mapping[str, str]) -> str:
    if match.groupdict().get("vault"):
        url, label = _obsidian(vaults[match["root"].lower()], match["rest"])
        return _link(label, url)

    if match["url"]:
        url, cut = _trimmed(match["url"])
        return _link(_label(url), url) + cut

    return match[0]


def linkify(markdown: str, vaults: abc.Collection[Path]) -> str:
    """*markdown* with bare URLs, and `.md` paths under each expanded vault root, as links.

    Obsidian names a vault after its folder, so a root's basename is its vault name.
    """
    names = {s.lower(): root.name for root in vaults for s in _spellings(root)}
    return _tokens(vaults).sub(lambda match: _replace(match, names), markdown)
