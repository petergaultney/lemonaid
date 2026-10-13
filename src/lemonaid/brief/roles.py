"""The roles a lemon has, derived from its brief and its relatives' briefs; nobody declares one.

- A reviewer of PR N has a brief with a `Reviews:` line naming N (written by `brief new --child
  --template review --pr N`).
- An author of PR N has N in its `### PRs` table and is not N's reviewer.
- A lead has children, and some of their briefs name an `Output-Doc:`.
"""

import sqlite3
import typing as ty
from collections import abc
from pathlib import Path

from ..lineage import links
from . import layout, lemon, output_doc, pr_table, reviews, status


class PR(ty.NamedTuple):
    repo: str  # owner/name
    number: int


def reviewing(text: str) -> PR | None:
    """The PR the brief *text* reviews."""
    found = reviews.read(text)

    return PR(*found) if found else None


def authoring(text: str) -> list[PR]:
    """The PRs in *text*'s `### PRs` table that it doesn't review."""
    now = layout.parse(status.split(text).now)
    at = layout.find(now, "PRs")
    if at is None:
        return []

    rows, _ = pr_table.parse(now.sections[at].body)
    return [
        pr
        for row in rows
        if (found := pr_table.target(row.pr))
        and (pr := PR(found[0], int(found[1]))) != reviewing(text)
    ]


def _briefs(
    conn: sqlite3.Connection, lemon_ids: abc.Iterable[str]
) -> abc.Iterator[tuple[str, str]]:
    """(Lemon-ID, brief text) of each lemon whose brief file exists."""
    for lemon_id in lemon_ids:
        if (path := lemon.brief_of(conn, lemon_id)) and path.is_file():
            yield lemon_id, path.read_text()


def _relatives(conn: sqlite3.Connection, lemon_id: str) -> list[str]:
    """Its children and its siblings: where a reviewer started by it or by its lead lives."""
    parent = links.parent_of(conn, lemon_id)
    siblings = links.children_of(conn, parent) if parent else []

    return [*links.children_of(conn, lemon_id), *(s for s in siblings if s != lemon_id)]


def review_docs(conn: sqlite3.Connection, lemon_id: str, pr: PR) -> list[Path]:
    """The output docs of the briefs, among its relatives, that review *pr*."""
    return [
        doc
        for _, text in _briefs(conn, _relatives(conn, lemon_id))
        if reviewing(text) == pr and (doc := output_doc.read(text))
    ]


def child_docs(conn: sqlite3.Connection, lemon_id: str) -> list[Path]:
    """The output docs of its children whose briefs aren't done."""
    return [
        doc
        for _, text in _briefs(conn, links.children_of(conn, lemon_id))
        if status.split(text).status != "done" and (doc := output_doc.read(text))
    ]
