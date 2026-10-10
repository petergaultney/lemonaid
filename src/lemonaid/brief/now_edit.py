"""The routine edits to a brief's `## Now`: add, replace, or remove one bullet.

Every edit rewrites the section in the order `layout` gives it, and leaves the
rest of the brief as written.
"""

import dataclasses
import re
from collections import abc

from . import layout, store

_FENCE = re.compile(r"(```|~~~)")
_NAMES = ("Needs", "Running", "Waiting on", "Next", "PRs", "Done")


class EditError(ValueError):
    pass


def heading_name(heading: str) -> str:
    """*heading* as the rules spell it; `Needs <who>` keeps who it names."""
    found = layout.rank(heading)
    if found is None:
        raise EditError(f"{heading!r} is not one of: Needs <who>, {', '.join(_NAMES[1:])}")

    return heading.strip()[:1].upper() + heading.strip()[1:] if found == 0 else _NAMES[found]


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
    rendered = layout.render(layout.ordered(dataclasses.replace(now, tail=tail))).splitlines()
    body = ["", *rendered, ""] if rendered else [""]
    return "\n".join([*above, *body, *below]).rstrip("\n") + "\n"


def now_of(text: str) -> layout.Now:
    lines = text.splitlines()
    start, end = layout.bounds(lines) or (0, 0)
    return layout.parse("\n".join(lines[start:end]))


def with_section(
    text: str, heading: str, change: abc.Callable[[tuple[str, ...]], abc.Sequence[str]]
) -> str:
    """*text* with the body of the section *heading* names replaced by *change* of it.

    A missing section starts empty, and one left empty is removed.
    """
    now = now_of(text)
    at = layout.find(now, heading)
    body = tuple(change(now.sections[at].body if at is not None else ()))
    sections = list(now.sections)
    if at is None:
        sections.append(layout.Section(heading_name(heading), body))
    else:
        sections[at] = dataclasses.replace(sections[at], body=body)
    return with_now(text, dataclasses.replace(now, sections=tuple(sections)))


def _item(bullet: str) -> tuple[str, ...]:
    first, *rest = bullet.strip().splitlines() or [""]
    if not first.strip():
        raise EditError("The bullet is empty")

    return (f"- {layout.bullet_text([first]) or first.strip()}", *rest)


def add(text: str, heading: str, bullet: str) -> str:
    """Add *bullet* to the end of the section *heading* names, or to the top of Done."""
    if layout.rank(heading) == layout.ORDER.index("prs"):
        raise EditError("The PR table has its own verb: `lemonaid brief pr add`")

    heading_name(heading)
    item = _item(bullet)
    at_top = layout.rank(heading) == layout.ORDER.index("done")
    return with_section(text, heading, lambda body: [*item, *body] if at_top else [*body, *item])


def _matching(now: layout.Now, lead: str) -> list[tuple[int, int]]:
    """(section, item) of every bullet outside the PR table whose text starts with *lead*."""
    wanted = lead.strip().lower()
    if not wanted:
        raise EditError("Name the bullet by the start of its text")

    return [
        (s, i)
        for s, section in enumerate(now.sections)
        if layout.rank(section.heading) != layout.ORDER.index("prs")
        for i, item in enumerate(layout.bullets(section.body))
        if layout.bullet_text(item).lower().startswith(wanted)
    ]


def _the_one(now: layout.Now, lead: str) -> tuple[int, int]:
    found = _matching(now, lead)
    if len(found) == 1:
        return found[0]

    if not found:
        raise EditError(f"No bullet in ## Now starts with {lead!r}")

    shown = " | ".join(
        layout.bullet_text(layout.bullets(now.sections[s].body)[i])[:40] for s, i in found[:3]
    ) + (f" (+{len(found) - 3} more)" if len(found) > 3 else "")
    raise EditError(f"{len(found)} bullets start with {lead!r}; use more of one: {shown}")


def _with_item(text: str, lead: str, replacement: abc.Sequence[str]) -> str:
    now = now_of(text)
    s, i = _the_one(now, lead)
    items = layout.bullets(now.sections[s].body)
    body = [line for item in [*items[:i], replacement, *items[i + 1 :]] for line in item]
    sections = list(now.sections)
    sections[s] = dataclasses.replace(sections[s], body=layout.trimmed(body))
    return with_now(text, dataclasses.replace(now, sections=tuple(sections)))


def replace(text: str, lead: str, bullet: str) -> str:
    """Replace the one bullet whose text starts with *lead*, and what is under it."""
    return _with_item(text, lead, _item(bullet))


def remove(text: str, lead: str) -> str:
    return _with_item(text, lead, ())
