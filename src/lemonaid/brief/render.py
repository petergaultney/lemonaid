"""Markdown for where a place's work stands, shared by the popup, pager and sidebar.

Each brief opens with who its lemon is and its status, then what it needs from
a person, whatever order the worker wrote `## Now` in. Where the lemon runs, which
file the brief is, and how old it is come once, at the bottom.
"""

import re
from collections import abc
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

    return f"**{label}:** {text}" if "\n" not in text else f"**{label}:**\n\n{text}"


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


def _prs(text: str, cwd: Path | None, pr_state: pr.Lookup) -> str:
    states = [
        " ".join(part for part in (pr.label(ref), pr_state(ref, cwd)) if part)
        for ref in pr.refs(text)
    ]
    return f"**PR:** {', '.join(states)}" if states else ""


def _block(
    brief: status.Brief,
    lemon: target.Identity | None,
    in_session: bool,
    detail: str,  # "full" (the task below a rule), "now", or "compact"
    pr_state: pr.Lookup,
) -> str:
    parts = status.split(brief.text)
    parsed = now.parse(parts.now)
    title = _display_title(parts.title) or brief.name or "Work status"
    cwd = Path(lemon.place) if lemon and lemon.place else brief.path.parent
    return "\n\n".join(
        part
        for part in (
            f"### {_who(lemon, in_session)}" if lemon else f"### {title}",
            "  \n".join(
                line
                for line in (
                    f"**Status:** {parts.status or parts.raw_status or '(no Status line)'}",
                    _prs(brief.text, cwd, pr_state),
                )
                if line
            ),
            _needs(parsed.needs_label, parsed.needs) if parsed.needs else "",
            f"**{title}**" if lemon else "",
            *_labelled(parsed, detail == "compact"),
            *(["---", parts.rest] if detail == "full" and parts.rest else []),
        )
        if part
    )


def _footer(
    briefs: abc.Sequence[status.Brief],
    lemons: abc.Mapping[Path, target.Identity],
    in_session: bool,
    now_seconds: float,
) -> str:
    places = [
        " · ".join(part for part in (lemon.directory, lemon.branch) if part)
        for brief in briefs
        if (lemon := lemons.get(brief.path))
    ]
    files = [
        " · ".join(
            part
            for part in (
                f"w{lemon.tmux_window}" if in_session and lemon else "",
                f"`{display.home_path(brief.path)}`",
                f"updated {status.age(now_seconds - brief.mtime)}",
            )
            if part
        )
        for brief in briefs
        for lemon in [lemons.get(brief.path)]
    ]
    return "  \n".join(f"*{line}*" for line in [*dict.fromkeys(p for p in places if p), *files])


def _window_order(lemon: target.Identity | None) -> tuple[int, str]:
    window = lemon.tmux_window if lemon else ""
    return (int(window), "") if window.isdigit() else (1 << 30, window)


def _briefs(
    briefs: abc.Sequence[status.Brief],
    found: target.Target,
    now_seconds: float,
    pr_state: pr.Lookup,
) -> str:
    lemons = (
        {brief.path: found.lemon for brief in briefs}
        if found.lemon
        else {b.path: lemon for b in briefs if (lemon := found.identities.get(b.path))}
    )
    in_session = found.lemon is None and bool(lemons)
    ordered = (
        sorted(briefs, key=lambda b: _window_order(lemons.get(b.path))) if in_session else briefs
    )
    blocks = [
        _block(
            brief,
            lemons.get(brief.path),
            in_session,
            "full" if len(briefs) == 1 else "now" if i == 0 or not in_session else "compact",
            pr_state,
        )
        for i, brief in enumerate(ordered)
    ]
    return "\n\n---\n\n".join([*blocks, _footer(ordered, lemons, in_session, now_seconds)])


def markdown(found: target.Target, now_seconds: float, pr_state: pr.Lookup) -> str:
    located = status.find(found.attached, found.dirs, found.place, found.names, now_seconds)
    body = located if isinstance(located, str) else _briefs(located, found, now_seconds, pr_state)
    return "\n\n".join(
        part
        for part in (found.header, "---" if found.header.startswith("# ") else "", body)
        if part
    )
