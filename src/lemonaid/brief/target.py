"""Which directories and brief names belong to a session, from the inbox and tmux.

The TUI and the CLI both resolve through here, so a session's brief is the same
whichever way it is asked for.
"""

import dataclasses
import json
from collections import abc
from pathlib import Path

from ..inbox import db, model_label
from . import display, session


@dataclasses.dataclass(frozen=True)
class Identity:
    """Who a lemon is and where it runs, as recorded in its inbox row."""

    name: str = ""
    emoji: str = ""
    backend: str = ""
    model: str = ""
    tmux_session: str = ""
    tmux_window: str = ""
    directory: str = ""  # shortened for display
    branch: str = ""
    place: str = ""  # the directory `gh` resolves `PR #N` from


@dataclasses.dataclass(frozen=True)
class Target:
    attached: list[Path]  # briefs attached to these lemons; when any, nothing else is read
    dirs: list[Path]  # searched in order; the first holding a brief wins
    place: Path | None  # the session's directory; no brief is looked for above it
    names: list[str]  # candidate <name>s for .z/brief-<name>.md, most specific first
    title: str
    header: str = ""  # Markdown above everything: a session's name, or why no lemon is shown
    lemon: Identity | None = None  # the one lemon this target is for, if it is for one
    identities: dict[Path, Identity] = dataclasses.field(default_factory=dict)


def to_json(found: Target) -> str:
    return json.dumps(
        {
            "attached": [str(path) for path in found.attached],
            "dirs": [str(path) for path in found.dirs],
            "place": str(found.place) if found.place else "",
            "names": found.names,
            "title": found.title,
            "header": found.header,
            "lemon": dataclasses.asdict(found.lemon) if found.lemon else None,
            "identities": {
                str(path): dataclasses.asdict(identity)
                for path, identity in found.identities.items()
            },
        }
    )


def from_json(data: abc.Mapping) -> Target:
    """Raises KeyError, TypeError or ValueError for anything `to_json` didn't write."""
    return Target(
        [Path(path) for path in data["attached"]],
        [Path(path) for path in data["dirs"]],
        Path(data["place"]) if data["place"] else None,
        list(data["names"]),
        data["title"],
        data["header"],
        Identity(**data["lemon"]) if data["lemon"] else None,
        {Path(path): Identity(**value) for path, value in data["identities"].items()},
    )


def _unique(paths: abc.Iterable[Path | None]) -> list[Path]:
    return list(dict.fromkeys(p for p in paths if p is not None))


def _backend(notification: db.Notification) -> str:
    return notification.channel.partition(":")[0]


def identity(notification: db.Notification, emoji: str = "", place: Path | None = None) -> Identity:
    metadata = notification.metadata
    model = model_label.model_label(metadata.get("model"))
    cwd = metadata.get("cwd")
    return Identity(
        notification.name or "",
        emoji,
        _backend(notification).capitalize(),
        model[0] if model else "",
        str(metadata.get("tmux_session") or ""),
        str(metadata.get("tmux_window") or ""),
        display.home_path(Path(cwd)) if cwd else "",
        str(metadata.get("git_branch") or ""),
        str(place or cwd or ""),
    )


def for_notification(
    notification: db.Notification, attached: abc.Mapping[str, Path], emoji: str = ""
) -> Target:
    """The target for one inbox row: its attached brief, else its lemon's cwd, then its
    tmux session's directory. *attached* maps channels to their briefs."""
    tmux_session = notification.metadata.get("tmux_session") or ""
    cwd = notification.metadata.get("cwd")
    place = session.session_dir(tmux_session) if tmux_session else None
    return Target(
        [attached[notification.channel]] if notification.channel in attached else [],
        _unique([Path(cwd) if cwd else None, place]),
        place,
        session.names(tmux_session, _backend(notification), notification.name or ""),
        notification.name or tmux_session or (Path(cwd).name if cwd else ""),
        lemon=identity(notification, emoji, place),
    )


def for_session(
    tmux_session: str,
    notifications: abc.Iterable[db.Notification],
    attached: abc.Mapping[str, Path],
    window: str = "",
    emojis: abc.Mapping[str, str] | None = None,
) -> Target:
    """The target for a tmux session, from every active inbox row recorded in it.

    A session can hold several lemons (a worker and its reviewer). A *window*
    holding one of them picks it; otherwise, only when the session holds exactly
    one does that lemon's backend count as a brief name, since no one of them is
    more likely than the rest.
    """
    rows = sorted(
        (n for n in notifications if n.metadata.get("tmux_session") == tmux_session),
        key=lambda n: n.created_at,
        reverse=True,
    )
    if window:
        rows = [n for n in rows if str(n.metadata.get("tmux_window") or "") == window] or rows

    if len(rows) == 1:
        return for_notification(rows[0], attached, (emojis or {}).get(rows[0].channel, ""))

    place = session.session_dir(tmux_session)
    return Target(
        [attached[n.channel] for n in rows if n.channel in attached],
        _unique([*(Path(n.metadata["cwd"]) for n in rows if n.metadata.get("cwd")), place]),
        place,
        session.names(tmux_session),
        tmux_session,
        f"# {tmux_session} · {len(rows)} lemons"
        if rows
        else f"**No lemon recorded in {tmux_session}**",
        identities={
            attached[n.channel]: identity(n, (emojis or {}).get(n.channel, ""), place)
            for n in rows
            if n.channel in attached
        },
    )
