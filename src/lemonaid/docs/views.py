"""What `lemonaid docs` prints, from the index and the delivery log."""

import os
from collections import abc
from pathlib import Path

from . import frontmatter

_HOME = str(Path.home())


def shown(path: str | Path) -> str:
    text = str(path)
    return "~" + text[len(_HOME) :] if text == _HOME or text.startswith(_HOME + os.sep) else text


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _condition(item: abc.Mapping) -> str:
    if not item:
        return "every lemon"

    return ", ".join(
        f"not ({_condition(v)})" if k == "not" and isinstance(v, dict) else f"{k}: `{v}`"
        for k, v in item.items()
    )


def _trigger(trigger: frontmatter.Trigger) -> str:
    return " ".join(
        [
            f"{trigger.kind} `{trigger.pattern}`",
            *([f"(section {trigger.section})"] if trigger.section else []),
            *(["before"] if trigger.before else []),
        ]
    )


def table(docs: abc.Sequence[frontmatter.Doc]) -> list[str]:
    """Markdown tables of the packages, then of every doc with a package or triggers."""
    packages = [d for d in docs if d.lemons]
    members = [d for d in docs if d.packages or d.triggers]
    return [
        "| Package | For | Index |",
        "|---|---|---|",
        *(
            f"| {frontmatter.package_name(d)} | {_cell('<br>'.join(map(_condition, d.lemons)))} | "
            f"{_cell(shown(d.path))} |"
            for d in packages
        ),
        "",
        "| Doc | Packages | Triggers | Reminder |",
        "|---|---|---|---|",
        *(
            f"| {_cell(shown(d.path))} | {', '.join(d.packages)} | "
            f"{_cell('<br>'.join(map(_trigger, d.triggers)))} | {_cell(d.reminder)} |"
            for d in members
        ),
    ]


def _delivered(entry: abc.Mapping) -> str:
    source = f"package {entry['package']}" if "package" in entry else entry.get("trigger", "")
    target = shown(entry.get("doc", "")) + (f"#{entry['section']}" if entry.get("section") else "")
    return (
        f"  {entry.get('at', '')[11:19]}  {entry.get('delivery', ''):<8}  {target}"
        f"  ({source}, {entry.get('chars', 0):,} chars"
        + (", shadow: not delivered)" if entry.get("shadow") else ")")
    )


def session(entries: abc.Sequence[abc.Mapping], missing: abc.Sequence[str]) -> list[str]:
    """Each context window of one session's *entries*, and what it was given."""
    if not entries:
        return []

    first = entries[0]
    lines = [
        f"{first.get('harness')} {first.get('session')}, docs mode {entries[-1].get('mode')}",
    ]
    for entry in entries:
        if entry.get("kind") == "window":
            lines += [
                f"window {entry.get('window')}: {entry.get('source')} at {entry.get('at')} "
                f"in {shown(entry.get('cwd', ''))}",
                f"  packages: {', '.join(entry.get('packages') or []) or 'none'}",
            ]
        else:
            lines.append(_delivered(entry))
    if missing:
        lines.append(f"packages for it now that its window didn't get: {', '.join(missing)}")
    return lines


def holders(rows: abc.Iterable[tuple[abc.Mapping, abc.Mapping]]) -> list[str]:
    """(window line, last delivery) of each session holding a doc."""
    return [
        f"{w.get('harness')} {w.get('session')}  window {w.get('window')}, "
        f"{d.get('delivery')} at {d.get('at')}, in {shown(w.get('cwd', ''))}"
        for w, d in rows
    ]
