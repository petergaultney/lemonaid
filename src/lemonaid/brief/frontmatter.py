"""A brief's YAML frontmatter, and the header-line view the rest of lemonaid parses.

Briefs used to keep their metadata in header lines under the title (`Brief-ID: ...`,
`Status: ...`). They now keep it in a frontmatter block, but lemonaid's parsers and
edits still work on header lines: `legacy` renders the block's fields as those lines
under the title, and `frontmatter_edit.carried` moves the header lines an edit leaves
back into the block.
"""

import datetime
import re
from collections import abc

import yaml

# Header-line label (lowercased) and its frontmatter key, in the order `legacy` renders them.
FIELDS = (
    ("brief-id", "brief-id"),
    ("status", "status"),
    ("parent", "parent"),
    ("output-doc", "output-doc"),
    ("area", "area"),
    ("groups", "groups"),
    ("hidden", "hidden"),
    ("name words", "name-words"),
)
_LABELS = {
    "brief-id": "Brief-ID",
    "status": "Status",
    "parent": "Parent",
    "output-doc": "Output-Doc",
    "area": "Area",
    "groups": "Groups",
    "hidden": "Hidden",
    "name-words": "Name words",
}
_HEADER = re.compile(
    r"(?P<label>Brief-ID|Lemon-ID|Status|Parent|Output-Doc|Area|Groups|Hidden|Name words"
    r"|type|created):(?P<value>.*)",
    re.IGNORECASE,
)
_SECTION = re.compile(r"#{1,2}\s")
_FENCE = re.compile(r" {0,3}(?P<marks>`{3,}|~{3,})")
_NOW = re.compile(r"##\s+now\s*", re.IGNORECASE)
_LABEL_KEYS = {
    **{label: key for label, key in FIELDS},
    "lemon-id": "brief-id",
    "type": "type",
    "created": "created",
}
# The fields a brief may also carry as lines inside `## Now` (see `layout.is_field`).
_NOW_FIELDS = ("parent", "output-doc", "area", "groups")
_SCALARS = (str, int, float, bool, datetime.date)
OLD_CONTRIBUTORS = "edited-by"  # what `contributors` was called in older briefs


KEY = re.compile(r"(?P<key>[^\s#:][^:]*?)\s*:(\s|$)")


def split(text: str) -> tuple[list[str] | None, str]:
    """The block's lines, between its `---` lines, and the body after it; None without one."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return None, text

    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() in ("---", "...")), None)
    if end is None:
        return None, text

    return lines[1:end], "\n".join(lines[end + 1 :])


def has_block(text: str) -> bool:
    return split(text)[0] is not None


def parsed(block: abc.Sequence[str]) -> dict:
    """The block's mapping; raises ValueError when it isn't one."""
    try:
        loaded = yaml.safe_load("\n".join(block))
    except yaml.YAMLError as error:
        raise ValueError(f"The frontmatter isn't valid YAML: {error}".splitlines()[0]) from None

    if loaded is None:
        return {}

    if not isinstance(loaded, dict):
        raise ValueError("The frontmatter isn't a mapping of keys to values")

    return loaded


def fields(text: str) -> dict:
    """The frontmatter of *text* as a mapping, {} without a block; raises ValueError if bad."""
    block, _ = split(text)
    return parsed(block) if block is not None else {}


def readable(block: abc.Sequence[str]) -> dict:
    """The block's mapping, or its plain `key: value` lines when the YAML doesn't parse."""
    try:
        return parsed(block)
    except ValueError:
        return {
            match["key"]: line[match.end() :].strip()
            for line in block
            if (match := KEY.match(line)) and line[match.end() :].strip()
        }


def contributors(values: abc.Mapping) -> list:
    """The `contributors` list of a parsed block, read from `edited-by` in an older one."""
    found = values.get("contributors", values.get(OLD_CONTRIBUTORS)) or []
    return found if isinstance(found, list) else [found]


def shown(key: str, value: object) -> str | None:
    """*value* as its header line shows it, or None when one line can't hold it."""
    if key == "hidden":
        return "yes" if value is True or str(value).lower() in ("yes", "true") else ""

    if value is None:
        return ""

    items = value if isinstance(value, list) else [value]
    if not all(isinstance(item, _SCALARS) for item in items):
        return None

    text = ", ".join(str(item) for item in items)
    separator = "," in "".join(str(item) for item in items) and isinstance(value, list)
    return None if "\n" in text or "\r" in text or separator else text


def legacy(text: str) -> str:
    """*text* with its block's fields as header lines under the title; unchanged without a block."""
    block, body = split(text)
    if block is None:
        return text

    values = readable(block)
    headers = [
        f"{_LABELS[key]}: {line}"
        for _, key in FIELDS
        if key in values and (line := shown(key, values[key]))
    ]
    lines = body.split("\n")
    at = 1 if lines and lines[0].startswith("# ") else 0
    rest = lines[at:]
    if not headers:
        return body

    gap = [""] if rest and rest[0].strip() else []
    return "\n".join([*lines[:at], *([""] if at else []), *headers, *gap, *rest])


def _unfenced(lines: abc.Sequence[str]) -> list[bool]:
    """For each line, whether it is outside a code fence (a fence line itself is not).

    A fence closes only on a line of the same marker, at least as long, with nothing
    after it, as `sections.unfenced_lines` reads them.
    """
    outside: list[bool] = []
    fence = ""
    for line in lines:
        match = _FENCE.match(line)
        if match and not fence:
            fence = match["marks"]
        elif (
            match
            and match["marks"][0] == fence[0]
            and len(match["marks"]) >= len(fence)
            and not line[match.end() :].strip()
        ):
            fence = ""
        else:
            outside.append(not fence)
            continue

        outside.append(False)
    return outside


def region_end(lines: abc.Sequence[str]) -> int:
    """Where the header region ends: the first section heading after the title."""
    outside = _unfenced(lines)
    return next(
        (i for i in range(1, len(lines)) if outside[i] and _SECTION.match(lines[i])), len(lines)
    )


def _now(lines: abc.Sequence[str], outside: abc.Sequence[bool]) -> range:
    """The lines of the `## Now` section's body, or none."""
    start = next((i for i, line in enumerate(lines) if outside[i] and _NOW.fullmatch(line)), None)
    if start is None:
        return range(0)

    end = next(
        (i for i in range(start + 1, len(lines)) if outside[i] and _SECTION.match(lines[i])),
        len(lines),
    )
    return range(start + 1, end)


def header_lines(lines: abc.Sequence[str]) -> list[tuple[int, str, str]]:
    """The (index, key, value) of each header line, in order.

    Header lines are the ones above the first section, and `Parent:`, `Output-Doc:`,
    `Area:` and `Groups:` lines in `## Now`; none inside a code fence counts.
    """
    end = region_end(lines)
    outside = _unfenced(lines)
    now = _now(lines, outside)
    found = []
    for i, line in enumerate(lines):
        match = _HEADER.fullmatch(line.rstrip()) if outside[i] else None
        key = _LABEL_KEYS[match["label"].lower()] if match else ""
        if match and (i < end or (i in now and key in _NOW_FIELDS)):
            found.append((i, key, match["value"].strip()))
    return found


def taken(lines: abc.Sequence[str]) -> tuple[dict[str, str], list[str]]:
    """The header lines' values by key, first wins, and *lines* without them."""
    found: dict[str, str] = {}
    gone = set()
    for i, key, value in header_lines(lines):
        found.setdefault(key, value)
        gone.add(i)
    return found, [line for i, line in enumerate(lines) if i not in gone]


def stray_labels(text: str) -> list[str]:
    """The labels of header lines in the body of *text*, a brief with a block."""
    block, body = split(text)
    if block is None:
        return []

    lines = body.split("\n")
    outside = _unfenced(lines)
    return [
        match["label"]
        for i, line in enumerate(lines[: region_end(lines)])
        if outside[i] and (match := _HEADER.fullmatch(line.rstrip()))
    ]
