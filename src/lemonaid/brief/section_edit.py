"""Edits scoped to arbitrary headings and their direct bullets."""

from collections import abc

from . import layout, sections, store


def change(
    text: str,
    name: str,
    update: abc.Callable[[tuple[str, ...]], abc.Sequence[str]],
    *,
    level: int = 2,
    parent: str = "Now",
    keep_empty: bool = False,
) -> str:
    heading = sections.find(text, name)
    lines = tuple(update(sections.body(text, heading) if heading else ()))
    if heading:
        return sections.replace(text, heading, lines, remove=not lines and not keep_empty)
    return sections.insert(text, name, lines, level, parent) if lines or keep_empty else text


def item(bullet: str) -> tuple[str, ...]:
    first, *rest = bullet.strip().splitlines() or [""]
    if not first.strip():
        raise ValueError("The bullet is empty")
    return (f"- {layout.bullet_text([first]) or first.strip()}", *rest)


def add(text: str, name: str, bullet: str) -> str:
    heading = sections.find(text, name)
    if heading:
        direct = sections.body(text, heading, direct=True)
        lines = (*item(bullet), *direct) if name.lower() == "done" else (*direct, *item(bullet))
        return sections.replace(text, heading, lines, direct=True)
    level = 3 if layout.rank(name) in (0, 1, 2) or name.lower() == "lemons" else 2
    if level == 3 and sections.find(text, "Now") is None:
        text = store.with_now(text, "")
    return sections.insert(text, name, item(bullet), level)


def _items(body: tuple[str, ...]) -> list[tuple[str, ...]]:
    outside = {i for i, _ in sections.unfenced_lines("\n".join(body))}
    items: list[list[str]] = []
    for i, line in enumerate(body):
        if not items or (i in outside and layout.bullet_text([line])):
            items.append([line])
        else:
            items[-1].append(line)
    return [tuple(lines) for lines in items]


def with_item(text: str, lead: str, replacement: abc.Sequence[str], name: str = "") -> str:
    if not lead.strip():
        raise ValueError("Name the bullet by the start of its text")
    selected = sections.find(text, name) if name else None
    if name and selected is None:
        raise ValueError(f"No heading {name!r}")
    candidates = []
    for heading in [selected] if selected else sections.scan(text):
        if heading.level == 1:
            continue
        items = _items(sections.body(text, heading, direct=True))
        for i, lines in enumerate(items):
            if layout.bullet_text(lines) and layout.bullet_text(lines).lower().startswith(
                lead.strip().lower()
            ):
                candidates.append((heading, items, i))
    if len(candidates) != 1:
        shown = ", ".join(
            f"{'#' * h.level} {h.name}: {layout.bullet_text(items[i])}"
            for h, items, i in candidates
        )
        raise ValueError(
            f"{len(candidates)} bullets start with {lead!r}: {shown}"
            if candidates
            else f"No bullet starts with {lead!r}"
        )
    heading, items, i = candidates[0]
    lines = layout.trimmed(
        [line for part in [*items[:i], replacement, *items[i + 1 :]] for line in part]
    )
    if not lines and heading.direct_end == heading.end:
        return sections.replace(text, heading, (), remove=True)
    return sections.replace(text, heading, lines, direct=True)
