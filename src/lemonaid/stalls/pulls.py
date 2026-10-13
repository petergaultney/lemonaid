"""The PRs that non-done briefs list, with the lemons and review doc around each.

An author's brief lists the PR in its `### PRs` table, with the review doc in the Review
column. A reviewer's brief is a `review-` brief that mentions the PR, and its pending
`watch pr --head` says which head it last reviewed.
"""

import dataclasses
import re
import urllib.parse
from collections import abc
from pathlib import Path

from ..brief import layout, pr, pr_table, status
from ..log import get_logger

_log = get_logger("stalls.pulls")
_HEAD = re.compile(r"watch pr\b.*--head[= ](?P<head>[0-9a-f]{7,40})\b")
_LINK = re.compile(r"\]\((?P<url>[^)\s]+)\)|`(?P<path>[^`]+)`")

Key = tuple[str, str]  # (`owner/repo`, number)


@dataclasses.dataclass(frozen=True)
class Lemon:
    channel: str
    path: Path
    name: str  # the part of its Brief-ID after the dot
    status: str
    mid_turn: bool
    since: float  # when it entered its status, or without one, its last report
    reviewer: bool


@dataclasses.dataclass(frozen=True)
class Pull:
    key: Key
    author: Lemon | None
    reviewer: Lemon | None
    doc: Path | None
    reviewed_head: str

    @property
    def briefs(self) -> list[Lemon]:
        return [lemon for lemon in (self.author, self.reviewer) if lemon]


def _text(lemon: Lemon) -> str:
    try:
        return lemon.path.read_text()
    except (OSError, UnicodeError) as error:
        _log.warning("could not read brief %s: %s", lemon.path, error)
        return ""


def _doc(cell: str, vaults: abc.Iterable[Path]) -> Path | None:
    """The review doc a Review cell names: a backticked path, or an `obsidian://` link."""
    found = _LINK.search(cell)
    if not found:
        return None

    if found["path"]:
        return Path(found["path"]).expanduser()

    query = urllib.parse.parse_qs(urllib.parse.urlsplit(found["url"]).query)
    rel, vault = query.get("file", [""])[0], query.get("vault", [""])[0]
    root = next((root for root in vaults if root.name == vault), None)
    return root / f"{rel}.md" if root and rel else None


def _rows(text: str) -> list[pr_table.Row]:
    now = layout.parse(status.split(text).now)
    at = layout.find(now, "PRs")
    return pr_table.parse(now.sections[at].body)[0] if at is not None else []


def _mentioned(text: str) -> set[Key]:
    return {found for ref in pr.refs(text) if (found := pr.repo_and_number(ref))}


def find(lemons: abc.Iterable[Lemon], vaults: abc.Iterable[Path]) -> list[Pull]:
    """A pull for each PR in the `### PRs` table of a brief that isn't `done`."""
    live = [lemon for lemon in lemons if lemon.status != "done"]
    reviewers = [(lemon, text) for lemon in live if lemon.reviewer and (text := _text(lemon))]
    pulls = []
    for author in (lemon for lemon in live if not lemon.reviewer):
        for row in _rows(_text(author)):
            key = pr_table.target(row.pr)
            if key is None:
                continue

            reviewer, text = next(
                ((lemon, text) for lemon, text in reviewers if key in _mentioned(text)),
                (None, ""),
            )
            head = _HEAD.search(text)
            pulls.append(
                Pull(key, author, reviewer, _doc(row.review, vaults), head["head"] if head else "")
            )
    return pulls
