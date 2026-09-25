"""Short clickable labels for the bare paths and URLs a worker writes in a brief.

A long URL wraps across lines, and a terminal that finds links by scanning text
loses it at the break. A Markdown link with a short label renders as one OSC 8
hyperlink per line instead, so it opens from anywhere on the label.

Vault notes (`~/work/vault/...md`, `~/trove/...md`) open in Obsidian. Code spans,
fenced blocks, autolinks and existing Markdown links are left as written.
"""

import re
import urllib.parse

_VAULTS = {"work/vault": "vault", "trove": "trove"}
_MAX_LABEL = 40
_TRAILING = ".,;:!?'\""

_PROTECTED = (
    r"(?P<fence>^(?P<ticks>```|~~~)[^\n]*\n.*?(?:^(?P=ticks)[^\n]*$|\Z))"
    r"|(?P<code>(?P<run>`+)(?:(?!\n\n).)+?(?P=run))"
    r"|(?P<link>!?\[[^\]\n]*\]\((?:<[^>\n]*>|[^)\s]*(?:\([^)\s]*\)[^)\s]*)*)[^)\n]*\))"
    r"|(?P<autolink><[a-z][a-z0-9+.-]*:[^>\s]*>)"
)
_BARE = (
    r"(?P<vault>(?<![\w/~])~/(?P<root>work/vault|trove)/(?P<rest>(?:(?!~/)[^\n`<>\[\]])*?\.md)(?![\w-]|\.\w))"
    r"|(?P<url>(?<![\w/])(?:https?|obsidian)://[^\s<>`\[\]]+)"
)
_TOKENS = re.compile(f"{_PROTECTED}|{_BARE}", re.MULTILINE | re.DOTALL | re.IGNORECASE)


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


def _obsidian(root: str, rest: str) -> tuple[str, str]:
    file = rest.removesuffix(".md")
    query = urllib.parse.urlencode(
        {"vault": _VAULTS[root], "file": file}, quote_via=urllib.parse.quote
    )
    return f"obsidian://open?{query}", _short(file.rsplit("/", 1)[-1])


def _label(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "obsidian":
        file = urllib.parse.parse_qs(parsed.query).get("file", [""])[0]
        return _short(file.rsplit("/", 1)[-1] or "obsidian")

    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc == "github.com" and len(parts) >= 4 and parts[2] in {"pull", "issues"}:
        return f"{parts[1]}#{parts[3]}"

    return _short("/".join([parsed.netloc, *(["…"] if len(parts) > 1 else []), *parts[-1:]]))


def _link(label: str, url: str) -> str:
    escaped = re.sub(r"([\\\[\]])", r"\\\1", label)
    return f"[{escaped}](<{url}>)"


def _replace(match: re.Match[str]) -> str:
    if match["vault"]:
        url, label = _obsidian(match["root"], match["rest"])
        return _link(label, url)

    if match["url"]:
        url, cut = _trimmed(match["url"])
        return _link(_label(url), url) + cut

    return match[0]


def linkify(markdown: str) -> str:
    return _TOKENS.sub(_replace, markdown)
