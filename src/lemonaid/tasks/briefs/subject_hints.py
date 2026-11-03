"""Hints that a brief's PRs and documents and its tasks' URLs don't match.

A PR or document a brief watches is usually some task's subject, and a task's PR or
document is usually watched by its holder's brief. Neither always holds, so these are
hints, never refusals.
"""

import shlex
import sqlite3
import urllib.parse
from pathlib import Path

from ... import brief
from ...brief import doc_table, layout, pr, pr_table, status
from ...inbox import db
from ..model import holding


def _key(url: str) -> str:
    """A PR as `owner/repo#number`, a file URL or path as its resolved path; anything else
    as written."""
    if url.startswith(("file://", "/")):
        return str(Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).resolve())

    found = pr.repo_and_number(url.rstrip("/"))
    return f"{found[0]}#{found[1]}" if found else url.rstrip("/")


def _watched(text: str) -> set[str]:
    now = layout.parse(status.split(text).now)
    at = layout.find(now, "PRs")
    rows = pr_table.parse(now.sections[at].body)[0] if at is not None else []
    return {
        *(_key(url) for row in rows if (url := pr_table.url(row.pr))),
        *(str(row.path) for row in doc_table.rows(text)),
    }


def unwatched(conn: sqlite3.Connection, holder: str, url: str) -> str:
    """A hint when *holder*'s brief lists a GitHub PR or file *url* under neither PRs nor
    Docs, else ""."""
    is_pr, is_file = pr.repo_and_number(url.rstrip("/")) is not None, url.startswith("file://")
    path = brief.lemon.brief_of(conn, holder.removeprefix("brief:")) if is_pr or is_file else None
    try:
        text = path.read_text() if path else ""
    except OSError:
        return ""
    if not text or _key(url) in _watched(text):
        return ""

    add = (
        f"lemonaid brief pr add --self {url} WORK"
        if is_pr
        else f"lemonaid brief doc add --self {shlex.quote(_key(url))} PURPOSE"
    )
    return f"Hint: {holder}'s brief doesn't watch {url}. If it should, its lemon runs `{add}`."


def unattached(conn: sqlite3.Connection, holder: str, url: str) -> str:
    """A hint when *holder* holds tasks with no URL and none with *url*, else ""."""
    held = holding.held_by(conn, holder)
    if any(t["subject_url"] and _key(t["subject_url"]) == _key(url) for t in held):
        return ""

    return "\n".join(
        f"Hint: your task task:{t['task_id']} ({t['description']}) has no URL. If this is"
        f" its subject, run `lemonaid task set-url {t['task_id']} {shlex.quote(url)} --reason TEXT`."
        for t in held
        if not t["subject_url"]
    )


def for_brief(path: Path, url: str) -> str:
    """`unattached` for the brief at *path*, "" when it has no Lemon-ID."""
    try:
        holder = brief.identity.from_path(path)
    except (OSError, ValueError):
        return ""

    with db.connect() as conn:
        return unattached(conn, holder, url)
