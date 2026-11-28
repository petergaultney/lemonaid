"""Dropping the `## Questions` entries an edit leaves without their Needs bullet.

An entry explains one ask. Once an edit removes the ask, the entry is stale, so it goes with
it instead of the edit being refused. An entry the edit itself adds without a matching bullet
is still refused by `brief check`.
"""

from collections import abc

from . import frontmatter, layout, now, questions, sections, status


def _check_view(text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    """The Questions entries, and those `brief check` finds without a Needs bullet."""
    parts = status.split(frontmatter.legacy(text))
    explained = questions.entries(parts.questions)
    return explained, questions.unmatched(now.parse(parts.now).needs, explained)


def _needs(text: str) -> str:
    """The Needs asks as `brief check` reads them, from *text* with its fenced lines left out,
    so an example inside a code fence is never taken for structure."""
    unfenced = "\n".join(line for _, line in sections.unfenced_lines(frontmatter.legacy(text)))
    return now.parse(status.split(unfenced).now).needs


def _asked(text: str, label: str, entry: str) -> bool:
    return not questions.unmatched(_needs(text), {label: entry})


def _without(text: str, heading: sections.Heading) -> str:
    """*text* without *heading*'s range, keeping the header field lines it holds."""
    lines = text.splitlines()
    fields = [line for line in lines[heading.start : heading.end] if layout.is_field(line)]
    kept = [*fields, ""] if fields else []
    return "\n".join([*lines[: heading.start], *kept, *lines[heading.end :]]).rstrip() + "\n"


def _without_entry(text: str, label: str) -> str:
    found = next(
        (
            h
            for h in sections.scan(text)
            if h.level == 3 and h.parent.lower() == "questions" and h.name == label
        ),
        None,
    )
    return _without(text, found) if found else text


def _without_empty_questions(text: str) -> str:
    found = next(
        (h for h in sections.scan(text) if h.level == 2 and h.name.lower() == "questions"), None
    )
    if found is None or any(
        line.strip() and not layout.is_field(line) for line in sections.body(text, found)
    ):
        return text

    return _without(text, found)


def pruned(before: str, after: str) -> tuple[str, list[str]]:
    """*after* without each Questions entry whose Needs bullet the edit from *before* removed,
    and the labels of the entries dropped."""
    explained, orphaned_before = _check_view(before)
    _, orphaned_after = _check_view(after)
    dropped = [
        label
        for label in orphaned_after
        if label in explained
        and label not in orphaned_before
        and _asked(before, label, explained[label])
        and not _asked(after, label, explained[label])
    ]
    result = after
    for label in dropped:
        result = _without_entry(result, label)
    return (_without_empty_questions(result) if dropped else after), dropped


def notice(dropped: abc.Sequence[str]) -> str:
    return (
        "Removed "
        + ", ".join(f"`### {label}`" for label in dropped)
        + " from ## Questions: the edit removed the Needs bullet it explained."
        if dropped
        else ""
    )
