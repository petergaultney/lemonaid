"""The `### PRs` table in `## Now`: one row per open PR, with columns Work, PR and Review.

The PR cell is a link to the pull request, labelled `<repo>#<number>`, and the
Review cell is a link to its review doc or empty.
"""

import dataclasses
import re
from collections import abc

from . import pr

_HEADER = ("work", "pr", "review")
_SEPARATOR = re.compile(r":?-+:?")
_PIPE = re.compile(r"(?<!\\)\|")
_LINK = re.compile(r"\[[^\]]*\]\(<?(?P<url>[^)>\s]+)>?\)")


@dataclasses.dataclass(frozen=True)
class Row:
    work: str
    pr: str  # the cell as written
    review: str


def _cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1):
        return None

    return [cell.strip() for cell in _PIPE.split(stripped[1:-1])]


def target(cell: str) -> tuple[str, str] | None:
    """(`owner/repo`, number) of the pull request a PR cell links to."""
    href = url(cell)
    return pr.repo_and_number(href) if href else None


def url(cell: str) -> str | None:
    """The link target as written in a PR cell."""
    match = _LINK.search(cell)
    return match["url"] if match else None


def parse(body: abc.Sequence[str]) -> tuple[list[Row], list[str]]:
    """The table's rows, and what is wrong with it."""
    lines = [line for line in body if line.strip()]
    if not lines:
        return [], []

    header, *rest = [_cells(line) for line in lines]
    problems = []
    if header is None or [cell.lower() for cell in header] != list(_HEADER):
        problems.append("### PRs: the first line is not the header `| Work | PR | Review |`")
    if not rest or rest[0] is None or not all(_SEPARATOR.fullmatch(c) for c in rest[0]):
        problems.append("### PRs: the header is not followed by a `|---|---|---|` line")

    rows: list[Row] = []
    seen: set[tuple[str, str]] = set()
    for line, cells in zip(lines[2:], rest[1:], strict=True):
        if cells is None or len(cells) != 3:
            problems.append(f"### PRs: not a three-column table row: {line.strip()[:60]}")
            continue

        row = Row(*cells)
        found = target(row.pr)
        if found is None:
            problems.append(f"### PRs: no pull-request link in {row.pr[:60]!r}")
        elif found in seen:
            problems.append(f"### PRs: {found[0]}#{found[1]} has two rows")
        else:
            seen.add(found)
        rows.append(row)

    return rows, problems


def render(rows: abc.Sequence[Row]) -> list[str]:
    if not rows:
        return []

    return [
        "| Work | PR | Review |",
        "|---|---|---|",
        *(f"| {row.work} | {row.pr} | {row.review} |".replace("|  |", "| |") for row in rows),
    ]


def _well_formed(body: abc.Sequence[str]) -> list[Row]:
    rows, problems = parse(body)
    if problems:
        raise ValueError("; ".join(problems) + " (fix the table by hand first)")

    return rows


def with_row(body: abc.Sequence[str], url: str, work: str, review: str | None) -> list[str]:
    """*body* with a row for the PR at *url*, replacing its row if it has one.

    `review` None keeps the review link already there.
    """
    found = pr.repo_and_number(url)
    if found is None:
        raise ValueError(f"{url} is not a pull-request URL")

    rows = _well_formed(body)
    repo, number = found
    cell = f"[{repo.split('/')[-1]}#{number}]({url})"
    work = work.replace("|", r"\|").strip()
    at = next((i for i, row in enumerate(rows) if target(row.pr) == found), None)
    if at is None:
        return render([*rows, Row(work, cell, review or "")])

    kept = rows[at].review if review is None else review
    return render([*rows[:at], Row(work, cell, kept), *rows[at + 1 :]])


def without(body: abc.Sequence[str], ref: str) -> list[str]:
    """*body* without the row for *ref*: a PR URL, or a number when only one row has it."""
    rows = _well_formed(body)
    by_url = pr.repo_and_number(ref)
    number = ref.strip().lstrip("#")
    matches = [
        i
        for i, row in enumerate(rows)
        if (found := target(row.pr))
        and (found == by_url or (by_url is None and found[1] == number))
    ]
    if not matches:
        raise ValueError(f"No row in ### PRs for {ref}")

    if len(matches) > 1:
        raise ValueError(f"Several rows in ### PRs are #{number}; name the PR by its URL")

    return render([row for i, row in enumerate(rows) if i != matches[0]])
