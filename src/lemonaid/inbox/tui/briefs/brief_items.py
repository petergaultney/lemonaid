"""Selectable Needs and saved answers, in their displayed order."""

import dataclasses
import hashlib
from collections import abc
from pathlib import Path

from ....brief import answer_archive, questions, render, sections
from ....config import KeybindingsConfig
from ....log import get_logger

_log = get_logger("tui.brief_items")

Choice = tuple[Path, str]


@dataclasses.dataclass(frozen=True)
class Item:
    choice: Choice
    kind: str
    label: str
    body: str


def _choice(path: Path, kind: str, body: str) -> Choice:
    return path, kind + ":" + hashlib.sha256(body.encode()).hexdigest()


def needs(section: render.Section) -> tuple[questions.Item, ...]:
    return section.questions or questions.items(
        section.needs_text, {label: "" for label in questions.labels(section.needs_text)}
    )


def entries(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    starts = [h.start for h in sections.scan(markdown) if h.level == 3]
    return [
        "\n".join(lines[start:end]).strip()
        for start, end in zip(starts, [*starts[1:], len(lines)], strict=False)
    ]


def _label(entry: str) -> str:
    question = entry.partition("**Question:**")[2].partition("**Answer:**")[0]
    return " ".join(
        line.removeprefix("> ").strip() for line in question.strip().splitlines()
    ) or entry.splitlines()[0].lstrip("# ")


def items(shown: abc.Sequence[render.Section], expanded: bool) -> tuple[Item, ...]:
    found = []
    for section in shown:
        if section.path is None:
            continue

        for need in needs(section):
            label = need.label or next(iter(questions.labels(need.text)), need.text)
            body = f"- {need.text}" + (f"\n\n{need.entry}" if need.entry else "")
            found.append(Item(_choice(section.path, "need", need.text), "need", label, body))
        for entry in entries(section.answers):
            found.append(
                Item(_choice(section.path, "answer", entry), "answer", _label(entry), entry)
            )
        if expanded:
            try:
                archived = answer_archive.read(section.path)
            except (OSError, ValueError) as cause:
                _log.warning("could not read answer archive for %s: %s", section.path, cause)
                archived = []
            for entry in archived:
                found.append(
                    Item(_choice(section.path, "archived", entry), "archived", _label(entry), entry)
                )
    return tuple(found)


def hint(item: Item, kb: KeybindingsConfig) -> str:
    moves = " ".join(key for key in (kb.question_previous, kb.question_next) if key)
    actions = (
        [(kb.answer, "answer"), (kb.answer_yes, "yes"), (kb.more_detail, "more detail")]
        if item.kind == "need"
        else [
            (kb.answer_archive, "archive this answer"),
            (kb.answer_archive_all, "all in brief"),
            (kb.answers_expand, "archives"),
        ]
        if item.kind == "answer"
        else [(kb.answers_expand, "collapse archives")]
    )
    label = {"need": "Needs", "answer": "Saved answer", "archived": "Archived answer"}[item.kind]
    short = item.label if len(item.label) <= 24 else item.label[:21] + "..."
    controls = " · ".join(
        [
            *([f"{moves} select"] if moves else []),
            *(f"{key} {action}" for key, action in actions if key),
        ]
    )
    return f"Selected {label}: {short}\n{controls}"
