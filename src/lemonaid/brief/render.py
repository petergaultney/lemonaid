"""Where a place's work stands, shared by the popup, pager and sidebar.

`view` sorts out what to show: one section per brief, each with who its lemon
is, its status and PRs, and a body of what the worker wrote, starting with what
it needs from a person, whatever order `## Now` was written in. The popup and
sidebar draw each section's identity as a card; `markdown` writes the whole
view as plain Markdown for lemons and scripts.
"""

import dataclasses
import re
from pathlib import Path

from . import display, now, pr, status, target

_GENERIC_TITLE_PREFIX = re.compile(r"^brief:\s*", re.IGNORECASE)


def _display_title(title: str) -> str:
    """The task itself, without the template's generic label."""
    return _GENERIC_TITLE_PREFIX.sub("", title, count=1).strip()


def _who(lemon: target.Identity, in_session: bool) -> str:
    model = f"{lemon.backend} / {lemon.model}" if lemon.model else lemon.backend
    name = " ".join(part for part in (lemon.emoji, lemon.name) if part)
    if in_session:
        return " · ".join(part for part in (f"w{lemon.tmux_window}", name, model) if part)

    location = ":".join(part for part in (lemon.tmux_session, lemon.tmux_window) if part)
    return " · ".join(part for part in (name, model, location) if part)


def _part(label: str, text: str) -> str:
    if not label:
        return text

    inline = "\n" not in text and not now.is_list(text)
    return f"**{label}:** {text}" if inline else f"**{label}:**\n\n{text}"


def _needs(label: str, text: str) -> str:
    return "\n".join(f"> {line}".rstrip() for line in _part(label, text).splitlines())


def _labelled(parsed: now.Now, compact: bool) -> list[str]:
    """Everything in Now but Needs, with Done last; compact keeps one line of Waiting on."""
    if compact:
        return [_part("Waiting on", now.summary(parsed.waiting_on))] if parsed.waiting_on else []

    return [
        _part(label, text)
        for label, text in (
            ("Waiting on", parsed.waiting_on),
            ("Next", parsed.next),
            ("", parsed.other),
            ("Done", parsed.done),
        )
        if text
    ]


@dataclasses.dataclass(frozen=True)
class Section:
    lemon: target.Identity | None
    title: str
    state: str  # one of store.STATES, or ""
    raw_status: str
    prs: tuple[tuple[str, str], ...]  # (label, live state or "")
    path: Path
    mtime: float
    body: str  # Markdown: Needs, the title under a lemon, the rest of Now, then the task


@dataclasses.dataclass(frozen=True)
class View:
    header: str  # Markdown: a session's name (`# ...`), or why no lemon is named
    in_session: bool  # the sections are the lemons of one tmux session
    sections: tuple[Section, ...]
    fallback: str  # Markdown shown when there is no brief


def _prs(text: str, cwd: Path | None, pr_state: pr.Lookup) -> tuple[tuple[str, str], ...]:
    return tuple((pr.label(ref), pr_state(ref, cwd)) for ref in pr.refs(text))


def _section(
    brief: status.Brief,
    lemon: target.Identity | None,
    detail: str,  # "full" (the task below a rule), "now", or "compact"
    pr_state: pr.Lookup,
) -> Section:
    parts = status.split(brief.text)
    parsed = now.parse(parts.now)
    title = _display_title(parts.title) or brief.name or "Work status"
    body = "\n\n".join(
        part
        for part in (
            _needs(parsed.needs_label, parsed.needs) if parsed.needs else "",
            f"**{title}**" if lemon else "",
            *_labelled(parsed, detail == "compact"),
            *(["---", parts.rest] if detail == "full" and parts.rest else []),
        )
        if part
    )
    return Section(
        lemon,
        title,
        parts.status,
        parts.raw_status,
        _prs(
            brief.text, Path(lemon.place) if lemon and lemon.place else brief.path.parent, pr_state
        ),
        brief.path,
        brief.mtime,
        body,
    )


def _window_order(lemon: target.Identity | None) -> tuple[int, str]:
    window = lemon.tmux_window if lemon else ""
    return (int(window), "") if window.isdigit() else (1 << 30, window)


def view(found: target.Target, now_seconds: float, pr_state: pr.Lookup) -> View:
    located = status.find(found.attached, found.dirs, found.place, found.names, now_seconds)
    if isinstance(located, str):
        return View(found.header, False, (), located)

    lemons = (
        {brief.path: found.lemon for brief in located}
        if found.lemon
        else {b.path: lemon for b in located if (lemon := found.identities.get(b.path))}
    )
    in_session = found.lemon is None and bool(lemons)
    ordered = (
        sorted(located, key=lambda b: _window_order(lemons.get(b.path))) if in_session else located
    )
    return View(
        found.header,
        in_session,
        tuple(
            _section(
                brief,
                lemons.get(brief.path),
                "full" if len(located) == 1 else "now" if i == 0 or not in_session else "compact",
                pr_state,
            )
            for i, brief in enumerate(ordered)
        ),
        "",
    )


def status_text(section: Section) -> str:
    return section.state or section.raw_status or "(no Status line)"


def where(lemon: target.Identity) -> str:
    return " · ".join(part for part in (lemon.directory, lemon.branch) if part)


def file_line(section: Section, in_session: bool, now_seconds: float) -> str:
    return " · ".join(
        part
        for part in (
            f"w{section.lemon.tmux_window}" if in_session and section.lemon else "",
            f"`{display.home_path(section.path)}`",
            f"updated {status.age(now_seconds - section.mtime)}",
        )
        if part
    )


def _markdown_section(section: Section, in_session: bool) -> str:
    prs = ", ".join(" ".join(part for part in pair if part) for pair in section.prs)
    return "\n\n".join(
        part
        for part in (
            f"### {_who(section.lemon, in_session)}" if section.lemon else f"### {section.title}",
            "  \n".join(
                line
                for line in (f"**Status:** {status_text(section)}", f"**PR:** {prs}" if prs else "")
                if line
            ),
            section.body,
        )
        if part
    )


def to_markdown(shown: View, now_seconds: float) -> str:
    places = dict.fromkeys(where(s.lemon) for s in shown.sections if s.lemon)
    footer = "  \n".join(
        f"*{line}*"
        for line in [
            *(p for p in places if p),
            *(file_line(s, shown.in_session, now_seconds) for s in shown.sections),
        ]
    )
    body = shown.fallback or "\n\n---\n\n".join(
        [*(_markdown_section(s, shown.in_session) for s in shown.sections), footer]
    )
    return "\n\n".join(
        part
        for part in (shown.header, "---" if shown.header.startswith("# ") else "", body)
        if part
    )


def markdown(found: target.Target, now_seconds: float, pr_state: pr.Lookup) -> str:
    return to_markdown(view(found, now_seconds, pr_state), now_seconds)
