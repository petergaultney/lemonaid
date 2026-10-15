"""Progress replacement and compatibility entry points for brief edits."""

import dataclasses
import re
from collections import abc

from . import layout, section_edit, sections, store

_FENCE = re.compile(r"(```|~~~)")
_KEPT = (layout.ORDER.index("prs"), layout.ORDER.index("docs"))


EditError = ValueError


def _field(line: str) -> str:
    return line.split(":", 1)[0]


def _with_fields(lines: abc.Sequence[str], given: dict[str, str]) -> list[str]:
    """*lines* with each field line outside a code fence replaced by, and taken from, *given*."""
    out = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
        out.append(
            given.pop(_field(line), line) if layout.is_field(line) and not in_fence else line
        )
    return out


def with_now(text: str, now: layout.Now) -> str:
    """*text* with `## Now` rewritten from *now*, added after the header if missing.

    `Parent:` and `Area:` are fields, one line each: a line *now* gives replaces
    the brief's line for that field, above Now or at its end, and a field *now*
    leaves out stays as it was.
    """
    lines = text.splitlines()
    if layout.bounds(lines) is None:
        lines = store.with_now(text, "").splitlines()
    start, end = layout.bounds(lines) or (len(lines), len(lines))
    given = {_field(line): line for line in now.tail}
    above = _with_fields(lines[:start], given)
    below = _with_fields(lines[end:], given)
    kept = layout.parse("\n".join(lines[start:end])).tail
    tail = (*(given.pop(_field(line), line) for line in kept), *given.values())
    rendered = layout.render(
        dataclasses.replace(now, tail=tail, sections=tuple(s for s in now.sections if s.body))
    ).splitlines()
    body = ["", *rendered, ""] if rendered else [""]
    return "\n".join([*above, *body, *below]).rstrip("\n") + "\n"


def now_of(text: str) -> layout.Now:
    lines = text.splitlines()
    start, end = layout.bounds(lines) or (0, 0)
    return layout.parse("\n".join(lines[start:end]))


def replace_progress(text: str, body: str, replace_all: bool = False) -> str:
    """Replace progress, retaining subscription tables omitted from the new body.

    Without *replace_all*, a body that omits a sub-heading the section has is refused.
    """
    promoted = {
        h.name.lower()
        for h in sections.scan(text)
        if h.level == 2 and h.name.lower() in sections.PROMOTED
    }
    carried = [
        h.name for h in sections.scan(body) if promoted and h.name.lower() in sections.PROMOTED
    ]
    if carried:
        raise EditError(
            f"{', '.join(carried)} belongs in its own section in this layout; use `brief section set`"
            " or `brief bullet add|set|rm` instead of `brief now`"
        )
    now = layout.parse(body)
    dropped = [
        section.heading
        for section in now_of(text).sections
        if layout.rank(section.heading) not in _KEPT
        and not ((at := layout.find(now, section.heading)) is not None and now.sections[at].body)
    ]
    if dropped and not replace_all:
        current = layout.render(now_of(text)).rstrip()
        raise EditError(
            f"This would drop {', '.join(f'### {h}' for h in dropped)} from ## Now, which is now:"
            f"\n\n{current}\n\nChange one line with `brief bullet add|set|rm`, or pass"
            " --replace-all to rewrite the section."
        )

    kept = tuple(
        section
        for section in now_of(text).sections
        if layout.rank(section.heading) in _KEPT and layout.find(now, section.heading) is None
    )
    return with_now(text, dataclasses.replace(now, sections=(*now.sections, *kept)))


def with_section(
    text: str, heading: str, change: abc.Callable[[tuple[str, ...]], abc.Sequence[str]]
) -> str:
    """*text* with the body of the section *heading* names replaced by *change* of it.

    A missing section starts empty, and one left empty is removed.
    """
    found = sections.find(text, heading)
    level = 3 if layout.rank(heading) in (0, 1, 2) or heading.lower() == "lemons" else 2
    if found is None and level == 3 and sections.find(text, "Now") is None:
        text = store.with_now(text, "")
    return section_edit.change(text, heading, change, level=level)


def add(text: str, heading: str, bullet: str) -> str:
    return section_edit.add(text, heading, bullet)


def replace(text: str, lead: str, bullet: str, heading: str = "") -> str:
    return section_edit.with_item(text, lead, section_edit.item(bullet), heading)


def remove(text: str, lead: str, heading: str = "") -> str:
    return section_edit.with_item(text, lead, (), heading)
