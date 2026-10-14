"""Whether a reviewer's author is a sibling: another brief under the same lead on the same PR."""

import sqlite3
from pathlib import Path

from .. import brief
from ..lineage import links as lineage_links
from .tui.rows import pr_numbers


def _own_pr(path: Path | None) -> tuple[str, str] | None:
    """(repo, number) of the one PR in the brief's `### PRs` table."""
    if path is None or not path.is_file():
        return None

    found = pr_numbers.brief_number(path.read_text())
    return brief.pr.repo_and_number(found.url) if found and found.url else None


def has_author_sibling(
    conn: sqlite3.Connection, brief_id: str, reviewer_text: str, lead_id: str
) -> bool:
    """A not-done, non-review brief under *lead_id* whose one PR the reviewer's brief links.

    A *lead_id* that lists the PR itself is the author, not a lead.
    """
    reviewed = {
        found for ref in brief.pr.refs(reviewer_text) if (found := brief.pr.repo_and_number(ref))
    }
    if not reviewed or _own_pr(brief.lemon.brief_of(conn, lead_id)) in reviewed:
        return False

    return any(
        _own_pr(path) in reviewed and brief.status.split(path.read_text()).status != "done"
        for child_id in lineage_links.children_of(conn, lead_id)
        if child_id != brief_id
        and not brief.identity.brief_description(child_id).startswith("review-")
        if (path := brief.lemon.brief_of(conn, child_id)) and path.is_file()
    )
