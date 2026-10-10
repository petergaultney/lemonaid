"""Where a place's work stands, shared by the popup, pager and sidebar.

`view` sorts out what to show: one section per brief, each with who its lemon
is, its status and PRs, and a body of what the worker wrote, starting with what
it needs from a person, whatever order `## Now` was written in. The popup and
sidebar draw each section's identity as a card; `markdown` writes the whole
view as plain Markdown for lemons and scripts.
"""

import dataclasses
import re
import textwrap
import typing as ty
from collections import abc
from pathlib import Path

from ..config import PlaceRoot
from . import display, identity, now, pr, project, questions, status, store, target

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
    """Everything in Now but Needs and Done; compact keeps one line each of Running and Waiting on."""
    if compact:
        return [
            _part(label, now.summary(text))
            for label, text in (("Running", parsed.running), ("Waiting on", parsed.waiting_on))
            if text
        ]

    return [
        _part(label, text)
        for label, text in (
            ("Running", parsed.running),
            ("Waiting on", parsed.waiting_on),
            ("Next", parsed.next),
            ("", parsed.other),
        )
        if text
    ]


class Child(ty.NamedTuple):
    state: str  # its brief's status
    name: str  # its session's name, or else its Lemon-ID's slug
    lemon_id: str


@dataclasses.dataclass(frozen=True)
class Section:
    lemon: target.Identity | None
    title: str
    state: str  # one of store.STATES; "" for none, which the inbox draws `active` or `idle`
    raw_status: str
    prs: tuple[tuple[str, str], ...]  # (label, live state or "")
    path: Path | None  # None for a lemon with no brief
    mtime: float
    body: str  # Markdown: Now up to Done, without Needs
    tail: str = ""  # Markdown after the children: Done, then the task
    needs_label: str = "Needs"
    needs_text: str = ""  # Markdown: what Now says the lemon needs, as written
    questions: tuple["questions.Item", ...] = ()  # Needs as items, when an entry explains one
    unmatched_questions: tuple[str, ...] = ()
    project: str = ""  # `ds-monorepo: apps/unified-asset`, or "" without a lemon or Area line
    held: str = ""  # the brief's own state, while its lemon is mid-turn and shows `state` instead
    lemon_id: str = ""
    compact: bool = False  # one of a session's later lemons, drawn in fewer lines
    # The rest are filled in by `family.added`.
    parent: str = ""  # its parent's Lemon-ID
    parent_name: str = ""  # its parent's session name, when lemonaid knows it
    children: tuple[Child, ...] = ()


@dataclasses.dataclass(frozen=True)
class View:
    header: str  # Markdown: a session's name (`# ...`), or why no lemon is named
    in_session: bool  # the sections are the lemons of one tmux session
    sections: tuple[Section, ...]
    fallback: str  # Markdown shown when there is no brief


def _prs(text: str, cwd: Path | None, pr_state: pr.Lookup) -> tuple[tuple[str, str], ...]:
    refs = pr.refs(text)
    return tuple((pr.label(ref, refs), pr_state(ref, cwd)) for ref in refs)


def _lemon_id(text: str) -> str:
    try:
        return identity.read(text)
    except ValueError:
        return ""  # `lemonaid brief check` reports a broken Lemon-ID line


def _section(
    brief: status.Brief,
    lemon: target.Identity | None,
    detail: str,  # "full" (the task below a rule), "now", or "compact"
    pr_state: pr.Lookup,
    roots: abc.Sequence[PlaceRoot],
) -> Section:
    parts = status.split(brief.text)
    parsed = now.parse(parts.now)
    explained = questions.entries(parts.questions)
    title = _display_title(parts.title) or brief.name or "Work status"
    body = "\n\n".join(_labelled(parsed, detail == "compact"))
    tail = "\n\n".join(
        part
        for part in (
            _part("Done", parsed.done) if parsed.done and detail != "compact" else "",
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
        tail,
        parsed.needs_label,
        parsed.needs,
        questions.items(parsed.needs, explained),
        questions.unmatched(parsed.needs, explained),
        project.label(roots, lemon.place, lemon.cwd, parts.area) if lemon else parts.area,
        lemon_id=_lemon_id(brief.text),
        compact=detail == "compact",
    )


def _item(item: questions.Item, selected: bool) -> str:
    lead = f"- {'▶ ' if selected else ''}{item.text}"
    return f"{lead}\n\n{textwrap.indent(item.entry, '  ')}\n" if item.entry else lead


def needs(section: Section, expanded: bool, selected: str = "") -> str:
    """Markdown for what a section's lemon needs, expanded with each question's entry.

    *selected* is the label of the question to mark, or "" for none.
    """
    warning = "\n".join(
        f"**Unmatched Questions:** `### {label}` has no matching Needs bullet."
        for label in section.unmatched_questions
    )
    if not section.needs_text:
        return warning

    if not (expanded and section.questions):
        return "\n\n".join(
            part for part in (_needs(section.needs_label, section.needs_text), warning) if part
        )

    matched = _needs(
        section.needs_label,
        "\n".join(
            _item(item, bool(selected) and item.label == selected) for item in section.questions
        ).strip(),
    )
    return "\n\n".join(part for part in (matched, warning) if part)


def _window_order(lemon: target.Identity | None) -> tuple[int, str]:
    window = lemon.tmux_window if lemon else ""
    return (int(window), "") if window.isdigit() else (1 << 30, window)


def _without_brief(lemon: target.Identity | None, why: str) -> Section:
    return Section(lemon, "", "", "no brief", (), None, 0, why)


def _member_brief(
    member: target.Target, taken: abc.Container[Path], now_seconds: float
) -> status.Brief | str:
    """This lemon's own brief, or Markdown saying why it has none.

    A `.z/` fallback counts only when it is named for this lemon or unnamed
    (`brief.md`), and no earlier lemon is already showing it: a name can be the
    session's, which every lemon in it shares, and a brief is one lemon's work.
    """
    located = status.find(member.attached, member.dirs, member.place, member.names, now_seconds)
    if isinstance(located, str):
        return located if member.attached else "No brief is attached, and there is none in `.z/`."

    if member.attached:
        return located[0]

    names = {name.lower() for name in member.names}
    candidates = [b for b in located if not b.name or b.name.lower() in names]
    own = [b for b in candidates if b.path not in taken]
    if len(own) == 1:
        return own[0]

    if own:
        return "No brief is attached, and several in `.z/` could be its."

    return (
        "No brief is attached; the one in `.z/` is shown for another lemon above."
        if candidates
        else "No brief is attached, and none in `.z/` is named for it."
    )


def _session_view(
    found: target.Target,
    now_seconds: float,
    pr_state: pr.Lookup,
    roots: abc.Sequence[PlaceRoot],
) -> View:
    members = sorted(found.members, key=lambda m: _window_order(m.lemon))
    sections: list[Section] = []
    taken: set[Path] = set()
    for member in members:
        brief = _member_brief(member, taken, now_seconds)
        if isinstance(brief, str):
            sections.append(_without_brief(member.lemon, brief))
            continue

        taken.add(brief.path)
        detail = "now" if not sections else "compact"
        sections.append(_section(brief, member.lemon, detail, pr_state, roots))

    return View(found.header, True, tuple(sections), "")


def view(
    found: target.Target,
    now_seconds: float,
    pr_state: pr.Lookup,
    roots: abc.Sequence[PlaceRoot] = (),
) -> View:
    """*roots* are the `[[places.roots]]` that name each section's project."""
    if found.members:
        return _session_view(found, now_seconds, pr_state, roots)

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
                roots,
            )
            for i, brief in enumerate(ordered)
        ),
        "",
    )


def status_text(section: Section) -> str:
    if section.state:
        return section.state

    word = section.raw_status.split(maxsplit=1)[0].lower() if section.raw_status.strip() else ""
    return "no Status: active or idle" if word in ("", *store.RETIRED) else section.raw_status


def where(lemon: target.Identity) -> str:
    return " · ".join(part for part in (lemon.directory, lemon.branch) if part)


def file_line(section: Section, in_session: bool, now_seconds: float) -> str:
    return " · ".join(
        part
        for part in (
            f"w{section.lemon.tmux_window}" if in_session and section.lemon else "",
            f"`{display.home_path(section.path)}`" if section.path else "",
            f"updated {status.age(now_seconds - section.mtime)}" if section.path else "",
        )
        if part
    )


def _child_line(child: Child) -> str:
    name = (
        [child.name]
        if child.name and child.name != identity.brief_description(child.lemon_id)
        else []
    )
    return " · ".join([f"- {child.state or '-'}", *name, identity.markdown_id(child.lemon_id)])


def _children(section: Section) -> str:
    if not section.children:
        return ""

    lines = "\n".join(_child_line(child) for child in section.children)
    return f"**Children:**\n\n{lines}"


def _parent(section: Section) -> str:
    return (
        f"{section.parent_name} ({identity.markdown_id(section.parent)})"
        if section.parent_name
        else identity.markdown_id(section.parent)
    )


def identity_lines(section: Section) -> list[str]:
    """Markdown lines for which lemon this is: its task, Lemon-ID and parent.

    A compact section puts the Lemon-ID and parent on one line. A section
    without a lemon names its task in its heading instead.
    """
    lemon_id = f"Brief-ID: {identity.markdown_id(section.lemon_id)}" if section.lemon_id else ""
    parent = f"Parent: {_parent(section)}" if section.parent else ""
    return [
        line
        for line in (
            f"**{section.title}**" if section.lemon else "",
            *(
                [" · ".join(part for part in (lemon_id, parent) if part)]
                if section.compact
                else [lemon_id, parent]
            ),
        )
        if line
    ]


def _markdown_section(section: Section, in_session: bool, expanded: bool) -> str:
    prs = ", ".join(" ".join(part for part in pair if part) for pair in section.prs)
    return "\n\n".join(
        part
        for part in (
            "### "
            + " · ".join(
                part
                for part in (
                    section.project,
                    _who(section.lemon, in_session) if section.lemon else section.title,
                )
                if part
            ),
            "  \n".join(
                [
                    *identity_lines(section),
                    " · ".join(
                        part
                        for part in (
                            f"**Status:** {status_text(section)}",
                            prs and f"**PR:** {prs}",
                        )
                        if part
                    ),
                ]
            ),
            needs(section, expanded),
            section.body,
            _children(section),
            section.tail,
        )
        if part
    )


def to_markdown(shown: View, now_seconds: float, expanded: bool = False) -> str:
    places = dict.fromkeys(where(s.lemon) for s in shown.sections if s.lemon)
    footer = "  \n".join(
        f"*{line}*"
        for line in [
            *(p for p in places if p),
            *(file_line(s, shown.in_session, now_seconds) for s in shown.sections if s.path),
        ]
    )
    body = shown.fallback or "\n\n---\n\n".join(
        [*(_markdown_section(s, shown.in_session, expanded) for s in shown.sections), footer]
    )
    return "\n\n".join(
        part
        for part in (shown.header, "---" if shown.header.startswith("# ") else "", body)
        if part
    )


def markdown(
    found: target.Target,
    now_seconds: float,
    pr_state: pr.Lookup,
    expanded: bool = False,
    roots: abc.Sequence[PlaceRoot] = (),
) -> str:
    return to_markdown(view(found, now_seconds, pr_state, roots), now_seconds, expanded)
