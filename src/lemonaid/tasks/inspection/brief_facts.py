"""Facts about a brief, and about the files it or its `Needs` names.

A file is captured by content: its fact names a copy, keyed by its hash, that a later
edit to the file can't change. Every local file a brief's `Needs` links to is observed
along with the brief, since a checker's `describe` can't know those links in advance.
"""

import hashlib
import shutil
import sqlite3
from collections import abc
from pathlib import Path

from ... import brief
from ...brief import doc_table, linked_asks, status
from ...inbox import status_since
from ...watch import relay_comments
from ..model import holding, identities
from . import live

_BRIEF_FIELDS = (
    "status",
    "needs",
    "waiting_on",
    "held",
    "signing_names",
    "status_since",
    "needs_since",
    "needs_links",
)

_FILE_FIELDS = ("exists", "modified_at", "headings", "sha256", "captured")


def _links(needs: str, vaults: abc.Collection[Path], base: Path) -> list[str]:
    """Each local file *needs* links to, as `PATH` or `PATH#HEADING`; a relative link is
    taken from *base*, the brief's own folder."""
    found = (
        (path, linked_asks.heading_of(match["url"]))
        for match in doc_table.LINK.finditer(needs)
        if (path := doc_table.path_of(match[0], vaults, base))
    )
    return list(
        dict.fromkeys(f"{path}#{heading}" if heading else str(path) for path, heading in found)
    )


def file(key: str, now: float) -> list[live.Fact]:
    """`exists`; and for a file that does, `modified_at`, its Markdown `headings` one per
    line, `sha256`, and `captured`, the path of its copy."""
    path = Path(key).expanduser()
    try:
        content, modified = path.read_bytes(), path.stat().st_mtime
    except FileNotFoundError:
        return [
            live.fact("file", key, "exists", "false", now),
            *(live.fact("file", key, f, "", now, "unavailable") for f in _FILE_FIELDS[1:]),
        ]
    except OSError:
        return [live.fact("file", key, f, "", now, "unavailable") for f in _FILE_FIELDS]

    digest = hashlib.sha256(content).hexdigest()
    captured = live.state_dir() / "task-captures" / digest
    if not captured.exists():
        captured.parent.mkdir(parents=True, exist_ok=True)
        temporary = captured.with_suffix(".tmp")
        temporary.write_bytes(content)
        shutil.move(temporary, captured)
    text = relay_comments.body_without_threads(content.decode(errors="replace"))
    return [
        live.fact("file", key, "exists", "true", now),
        live.fact("file", key, "modified_at", live.stamp(modified), now),
        live.fact("file", key, "headings", "\n".join(linked_asks.headings(text)), now),
        live.fact("file", key, "sha256", digest, now),
        live.fact("file", key, "captured", str(captured), now),
    ]


def facts(
    conn: sqlite3.Connection, key: str, now: float, vaults: abc.Collection[Path]
) -> list[live.Fact]:
    """`status`, `needs`, `waiting_on` and `held` (the IDs of the tasks it holds);
    `signing_names`, the names its lemon has signed comments with, current first;
    `status_since` and `needs_since`, when lemonaid first saw the current Status and Needs;
    and `needs_links`, one linked local file per line, with the facts for each file."""
    lemon_id = identities.current(conn, key) or key
    names = " ".join(
        dict.fromkeys(
            n for i in identities.names(conn, lemon_id) if (n := brief.identity.brief_name(i))
        )
    )
    try:
        path = brief.lemon.brief_of(conn, lemon_id)
        text, modified = (path.read_text(), path.stat().st_mtime) if path else ("", 0.0)
    except (LookupError, ValueError, OSError):
        path, text, modified = None, "", 0.0
    if path is None:
        return [live.fact("brief", key, field, "", now, "unavailable") for field in _BRIEF_FIELDS]

    parts = status.split(text)
    said = brief.now.parse(parts.now)
    links = _links(said.needs, vaults, path.parent)
    [status_at] = status_since.observe(conn, {path: (parts.status, modified)}).values()
    [needs_at] = status_since.observe_needs(conn, {path: (said.needs, modified)}).values()
    return [
        live.fact("brief", key, "status", parts.status, now),
        live.fact("brief", key, "needs", said.needs, now),
        live.fact("brief", key, "waiting_on", said.waiting_on, now),
        live.fact(
            "brief", key, "held", " ".join(t["task_id"] for t in holding.held_by(conn, key)), now
        ),
        live.fact("brief", key, "signing_names", names, now, "known" if names else "unknown"),
        live.fact("brief", key, "status_since", live.stamp(status_at), now),
        live.fact("brief", key, "needs_since", live.stamp(needs_at), now),
        live.fact("brief", key, "needs_links", "\n".join(links), now),
        *(
            f
            for link in dict.fromkeys(link.partition("#")[0] for link in links)
            for f in file(link, now)
        ),
    ]
