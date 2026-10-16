"""Compose selectable entry widgets without duplicating the rendered Answers prefix."""

from collections import abc

from textual.widget import Widget
from textual.widgets import Markdown

from ....brief import render, sections
from . import brief_items
from .brief_item_widget import ItemView


def widgets(
    section: render.Section,
    items: abc.Sequence[brief_items.Item],
    selected: brief_items.Choice | None,
    factory: abc.Callable[[str], Markdown],
) -> list[Widget]:
    own = [item for item in items if item.choice[0] == section.path]
    result: list[Widget] = []
    needs = [item for item in own if item.kind == "need"]
    if needs:
        result.append(factory(f"**{section.needs_label}:**"))
    for item in needs:
        quote = "\n".join(f"> {line}".rstrip() for line in item.body.splitlines())
        widget = ItemView(item, quote, factory, item.choice == selected)
        widget.set_class(bool(section.held), "brief-needs-mid-turn")
        result.append(widget)
    for label in section.unmatched_questions:
        result.append(
            factory(f"**Unmatched Questions:** `### {label}` has no matching Needs bullet.")
        )
    if section.answers:
        lines = section.answers.splitlines()
        start = next((h.start for h in sections.scan(section.answers) if h.level == 3), len(lines))
        result.append(factory("\n".join(lines[:start])))
    for item in own:
        if item.kind == "answer":
            result.append(ItemView(item, item.body, factory, item.choice == selected))
    archived = [item for item in own if item.kind == "archived"]
    if archived:
        result.append(factory(f"## Archived answers ({len(archived)})"))
        result.extend(
            ItemView(item, item.body, factory, item.choice == selected) for item in archived
        )
    rest = section.body.removeprefix(section.answers).lstrip()
    if rest:
        result.append(factory(rest))
    return result
