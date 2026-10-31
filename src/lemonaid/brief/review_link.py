"""A new reviewer's doc, filled into the Review cell of its PR's row in the briefs that list the PR.

The watcher wakes a brief's lemon for body edits only in a doc it can tie to a PR or
list for `All edits`, and reviewers write findings and verdicts in the body.
"""

import typing as ty
from collections import abc
from pathlib import Path

from ..inbox import db
from ..log import get_logger
from . import lemon, now_edit, pr_table, store

_log = get_logger("brief.review_link")


class Linked(ty.NamedTuple):
    briefs: list[Path]  # whose row for the PR now names the review doc
    unknown: list[str]  # targets that name no lemon


def _briefs(targets: abc.Iterable[str]) -> tuple[list[Path], list[str]]:
    paths, unknown = [], []
    with db.connect() as conn:
        for target in dict.fromkeys(t for t in targets if t):
            try:
                found = lemon.brief_of(conn, lemon.lemon_id(conn, target))
            except (LookupError, ValueError):
                found = None
            if found is None:
                unknown.append(target)
            else:
                paths.append(found)
    return paths, unknown


def link(targets: abc.Iterable[str], pr_url: str, review: str) -> Linked:
    """*targets* are lemons as `lemon.lemon_id` reads them: IDs, channels, brief names or paths."""
    paths, unknown = _briefs(targets)

    def change(text: str) -> str:
        return now_edit.with_section(
            text, "PRs", lambda body: pr_table.with_review(body, pr_url, review)
        )

    linked = []
    for path in paths:
        try:
            if change(path.read_text()) == path.read_text():
                continue

            store.edit(path, change)
        except (OSError, ValueError, store.ChangedUnderneath) as error:
            _log.warning("could not name %s's review doc in %s: %s", pr_url, path, error)
            continue
        linked.append(path)
    return Linked(linked, unknown)
