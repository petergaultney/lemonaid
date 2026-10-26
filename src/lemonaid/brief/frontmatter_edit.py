"""Writing a brief's frontmatter: moving an edit's header lines into the block.

Writes change only the lines of the keys whose values changed, so comments, key order
and keys lemonaid doesn't know survive. A brief without a block gets one the first
time lemonaid writes to it.
"""

import dataclasses
import datetime
import re
from collections import abc

import yaml

from . import frontmatter

# Every key lemonaid writes, in the order a block lists them.
ORDER = (
    "type",
    "created",
    "responsible-parties",
    "contributors",
    "brief-id",
    "parent",
    "brief-type",
    "status",
    "area",
    "output-doc",
    "groups",
    "hidden",
    "name-words",
)
_PARENT = re.compile(r"(?P<id>\S+?)(?:\s+\([^)]*\))?(?:,\s*\d{4}-\d{2}-\d{2})?")
_DATE_PREFIX = re.compile(r"(\d{4}-\d{2}-\d{2})-")
_TOP_KEY = re.compile(
    r"""(?:'(?P<single>[^']*)'|"(?P<double>[^"]*)"|(?P<plain>[^\s#'"?:\-][^:#]*?))\s*:(?:\s|$)"""
)


@dataclasses.dataclass(frozen=True)
class Defaults:
    """What a new block gets that header lines don't say."""

    created_on: datetime.date | None  # when the brief has no `created:` line to move
    responsible_parties: tuple[str, ...]


def _collapsed(lines: abc.Sequence[str]) -> list[str]:
    """*lines* with each run of blank lines cut to one, and no blank line first."""
    kept: list[str] = []
    for line in lines:
        if not line.strip() and (not kept or not kept[-1].strip()):
            continue

        kept.append(line)
    return kept


def parent_id(shown: str) -> str:
    """The Lemon-ID in a `Parent:` line's text, without its session and date."""
    return match["id"] if (match := _PARENT.fullmatch(shown)) else shown


def _value(key: str, shown: str) -> object:
    """A header line's text as the frontmatter value for *key*, or None for no key."""
    if key == "groups":
        return [name.strip() for name in shown.split(",") if name.strip()] or None

    if key == "name-words":
        return [word for word in re.split(r"[\s,]+", shown) if word] or None

    if key == "hidden":
        return True if shown.lower() in ("yes", "true") else None

    if key == "parent":
        return parent_id(shown) or None

    return shown or None


def _scalar(value: object) -> str:
    dumped = yaml.safe_dump(value, default_flow_style=True, allow_unicode=True, width=1 << 20)
    return dumped.removesuffix("\n...\n").strip()


def rendered(key: str, value: object) -> list[str]:
    """The block lines for *key* holding *value*."""
    if isinstance(value, list | tuple):
        return [f"{key}:", *(f"  - {_scalar(item)}" for item in value)]

    return [f"{key}: {_scalar(value)}"]


def _top_key(line: str) -> str | None:
    """The key a top-level `key: value` line starts, unquoted, or None for any other line."""
    if (match := _TOP_KEY.match(line)) is None:
        return None

    return next(name for name in match.group("single", "double", "plain") if name is not None)


def _extent(block: abc.Sequence[str], key: str) -> tuple[int, int] | None:
    """The lines *key*'s last top-level entry occupies, through its last value line.

    Comments and blank lines inside the value belong to it; ones after it don't.
    """
    starts = [i for i, line in enumerate(block) if _top_key(line) == key]
    if not starts:
        return None

    start = last = starts[-1]
    for i in range(start + 1, len(block)):
        if _top_key(block[i]) is not None:
            break

        if block[i].strip() and not block[i].lstrip().startswith("#"):
            last = i
    return start, last + 1


def with_key(block: abc.Sequence[str], key: str, value: object) -> list[str]:
    """*block* with *key* set to *value*, or removed for None, at its place in `ORDER`."""
    lines = list(block)
    found = _extent(lines, key)
    new = [] if value is None else rendered(key, value)
    if found:
        start, end = found
        return [*lines[:start], *new, *lines[end:]]

    if not new:
        return lines

    earlier = ORDER[: ORDER.index(key)] if key in ORDER else ORDER
    at = max((e[1] for k in earlier if (e := _extent(lines, k))), default=0)
    return [*lines[:at], *new, *lines[at:]]


def _created(shown: str, defaults: Defaults) -> list[str]:
    if shown:
        return [f"created: {shown}"]

    if defaults.created_on:
        return [f"created: {{ at: {defaults.created_on.isoformat()} }}"]

    return []


def _new_block(found: dict[str, str], defaults: Defaults) -> list[str]:
    created = _created(found.get("created", ""), defaults)
    by = re.search(r"\bby:\s*([^,}\s]+)", created[0]) if created else None
    return [
        f"type: {found.get('type') or 'Brief'}",
        *created,
        *rendered("responsible-parties", list(defaults.responsible_parties)),
        *(rendered("contributors", [by[1]]) if by else []),
    ]


def carried(after: str, before: str, defaults: Defaults) -> str:
    """*after*, an edit of `legacy(before)`, with its header lines moved into the block.

    A *before* with no block gets a new one; that is the brief's migration.
    """
    block, body = frontmatter.split(before)
    found, kept = frontmatter.taken(after.split("\n"))
    values = frontmatter.readable(block) if block is not None else {}
    lines = list(block) if block is not None else _new_block(found, defaults)
    for _, key in frontmatter.FIELDS:
        was = frontmatter.shown(key, values[key]) if key in values else ""
        if was is None and key not in found:
            continue  # not shown as a header line, so the edit left it alone

        if found.get(key, "") != was:
            lines = with_key(lines, key, _value(key, found.get(key, "")))

    end = frontmatter.region_end(kept)
    head, tail = _collapsed(kept[:end]), kept[end:]
    if block is not None:
        original = frontmatter.taken(body.split("\n"))[1]
        original_head = original[: frontmatter.region_end(original)]
        head = original_head if _collapsed(original_head) == head else head

    if head and tail and head[-1].strip():
        head.append("")
    return "\n".join(["---", *lines, "---", *head, *tail])


def _renamed(block: abc.Sequence[str], old: str, new: str) -> list[str]:
    """*block* with its top-level *old* key called *new*, unless it has a *new* key already."""
    lines = list(block)
    found = _extent(lines, old)
    if found is None or _extent(lines, new) is not None:
        return lines

    start = found[0]
    return [*lines[:start], f"{new}:{lines[start].split(':', 1)[1]}", *lines[start + 1 :]]


def with_editor(text: str, name: str) -> str:
    """*text* with *name* at the end of its block's `contributors`, unless it is there already.

    A block's `edited-by`, the key's older name, becomes `contributors` here.
    """
    block, body = frontmatter.split(text)
    if block is None:
        return text

    lines = _renamed(block, frontmatter.OLD_CONTRIBUTORS, "contributors")
    editors = frontmatter.contributors(frontmatter.readable(lines))
    if not name or name in editors:
        return text if lines == block else "\n".join(["---", *lines, "---", body])

    return "\n".join(["---", *with_key(lines, "contributors", [*editors, name]), "---", body])


def created_on(filename: str) -> datetime.date | None:
    """The date a brief's `<YYYY-MM-DD>-<slug>.md` filename starts with."""
    if not (match := _DATE_PREFIX.match(filename)):
        return None

    try:
        return datetime.date.fromisoformat(match[1])
    except ValueError:
        return None
