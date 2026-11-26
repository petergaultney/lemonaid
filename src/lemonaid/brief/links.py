"""Short clickable labels for the bare paths and URLs a worker writes in a brief.

A long URL wraps across lines, and a terminal that finds links by scanning text
loses it at the break. A Markdown link with a short label renders as one OSC 8
hyperlink per line instead, so it opens from anywhere on the label.

A `.md` path under a configured vault root, written from `~` or in full, opens
in Obsidian, and so does a `file://` or `obsidian://open?path=` link to one: by
vault name, so it opens on any machine with that vault. A Lemon-ID lemonaid knows, bare or alone in backticks, links to
`lemonaid://go/<Lemon-ID>`; any other `slug.Name` text stays as written. Path
cells in tables link even when written in backticks. Other code spans, fenced
blocks, autolinks and existing Markdown links are otherwise left as written.
"""

import re
import urllib.parse
from collections import abc
from pathlib import Path

from .. import obsidian

_MAX_LABEL = 40
_TRAILING = ".,;:!?'\""

_PROTECTED = (
    r"(?P<fence>^(?P<ticks>```|~~~)[^\n]*\n.*?(?:^(?P=ticks)[^\n]*$|\Z))"
    r"|(?P<code>(?P<run>`+)(?:(?!\n\n).)+?(?P=run))"
    r"|(?P<link>(?P<image>!)?\[(?:\\.|\[(?:\\.|[^\[\]\\\n])*\]|[^\[\]\\\n])*\]"
    r"\((?P<dest><[^>\n]*>|(?:\\.|[^()\s\\])*(?:\((?:\\.|[^()\s\\])*\)(?:\\.|[^()\s\\])*)*)[^)\n]*\))"
    r"|(?P<autolink><[a-z][a-z0-9+.-]*:[^>\s]*>)"
)
_DOC_CELL = (
    r"(?P<doccell>^[ \t]*\|[ \t]*(?P<doccode>`+)?"
    r"(?P<docpath>(?:~/|/)[^`\n|]+?)(?(doccode)(?P=doccode))[ \t]*(?=\|))"
)
_DOC_LINK_CELL = (
    r"(?P<doclink>^[ \t]*\|[ \t]*\[(?P<doclabel>(?:\\.|[^\]])*)\]"
    r"\(<?(?P<doctarget>[^>]+?)>?\)[ \t]*(?=\|))"
)
_URL = r"(?P<url>(?<![\w/])(?:https?|obsidian)://[^\s<>`\[\]]+)"
_LEMON = r"(?P<lemon>(?<![\w./~@:-])[\w-]+(?:\.[\w-]+)+(?![\w-]|\.\w))"
_FLAGS = re.MULTILINE | re.DOTALL | re.IGNORECASE
_MD_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")  # a backslash before ASCII punctuation


def go_url(lemon_id: str) -> str:
    return f"lemonaid://go/{urllib.parse.quote(lemon_id, safe='')}"


def _tokens(roots: abc.Iterable[Path]) -> re.Pattern[str]:
    spelled = sorted({s for root in roots for s in obsidian.spellings(root)}, key=len, reverse=True)
    if not spelled:
        return re.compile(f"{_PROTECTED}|{_DOC_LINK_CELL}|{_DOC_CELL}|{_URL}|{_LEMON}", _FLAGS)

    vault = (
        r"(?P<vault>(?<![\w/~])(?P<root>"
        + "|".join(re.escape(s) for s in spelled)
        + r")/(?P<rest>(?:(?!~/)[^\n`<>\[\]])*?\.md)(?![\w-]|\.\w))"
    )
    return re.compile(f"{_PROTECTED}|{_DOC_LINK_CELL}|{_DOC_CELL}|{vault}|{_URL}|{_LEMON}", _FLAGS)


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
    return obsidian.url(vault, rest), _short(rest.removesuffix(".md").rsplit("/", 1)[-1])


def _label(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "obsidian":
        file = urllib.parse.parse_qs(parsed.query).get("file", [""])[0]
        return _short(file.rsplit("/", 1)[-1] or "obsidian")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 4 and parts[2] in {"pull", "pulls", "issues"} and parts[3].isdigit():
        return f"{parts[1]}#{parts[3]}"

    return _short("/".join([parsed.netloc, *(["…"] if len(parts) > 1 else []), *parts[-1:]]))


def _dest_by_vault(match: re.Match[str], roots: abc.Collection[Path]) -> str:
    dest = match["dest"]
    angled = dest.startswith("<")
    written = _MD_ESCAPE.sub(r"\1", dest[1:-1] if angled else dest)
    url = obsidian.by_vault(written, roots)
    if url == written:
        return match[0]

    start, end = match.start("dest") - match.start(), match.end("dest") - match.start()
    return f"{match[0][:start]}{f'<{url}>' if angled else url}{match[0][end:]}"


def _link(label: str, url: str) -> str:
    escaped = re.sub(r"([\\\[\]])", r"\\\1", label)
    return f"[{escaped}](<{url}>)"


def _replace(
    match: re.Match[str],
    vaults: abc.Mapping[str, str],
    roots: abc.Collection[Path],
    lemons: abc.Container[str],
) -> str:
    if match.groupdict().get("lemon"):
        return (
            _link(match["lemon"], go_url(match["lemon"])) if match["lemon"] in lemons else match[0]
        )

    if match.groupdict().get("code") and (inner := match[0].strip("`").strip()) in lemons:
        return f"[`{inner}`](<{go_url(inner)}>)"

    if match.groupdict().get("doccell"):
        prefix = match[0].split("|", 1)[0]
        path = Path(match["docpath"].strip()).expanduser().resolve()
        url = obsidian.vault_link(path, roots) or path.as_uri()
        return prefix + "| " + _link(_short(path.name), url) + " "

    if match.groupdict().get("doclink"):
        label = re.sub(r"\\([\\\[\]])", r"\1", match["doclabel"])
        if label.startswith(("/", "~/")):
            prefix = match[0].split("|", 1)[0]
            url = obsidian.by_vault(match["doctarget"], roots)
            return prefix + "| " + _link(_short(Path(label).name), url) + " "
        start = match.start("doctarget") - match.start()
        target = obsidian.by_vault(match["doctarget"], roots)
        return f"{match[0][:start]}{target}{match[0][match.end('doctarget') - match.start() :]}"

    if match.groupdict().get("link") and not match["image"]:
        return _dest_by_vault(match, roots)

    if match.groupdict().get("vault"):
        url, label = _obsidian(vaults[match["root"].lower()], match["rest"])
        return _link(label, url)

    if match["url"]:
        written, cut = _trimmed(match["url"])
        url = obsidian.by_vault(written, roots)
        return _link(_label(url), url) + cut

    return match[0]


def linkify(
    markdown: str, vaults: abc.Collection[Path], lemons: abc.Container[str] = frozenset()
) -> str:
    """*markdown* with bare URLs, `.md` paths under each expanded vault root, and *lemons* as links.

    Obsidian names a vault after its folder, so a root's basename is its vault name.
    """
    names = {s.lower(): root.name for root in vaults for s in obsidian.spellings(root)}
    return _tokens(vaults).sub(lambda match: _replace(match, names, vaults, lemons), markdown)
