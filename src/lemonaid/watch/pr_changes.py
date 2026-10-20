"""One cheap GraphQL read of many PRs at once: enough of each to tell whether it changed.

A full snapshot (pr_activity) asks for up to 100 threads with 50 comments each, which
costs a point of quota per PR. This asks for scalars, counts, each check's status and each
thread's resolution, so `_BATCH` PRs cost about one point together (31 PRs measured 1).
"""

import itertools
import json
from collections import abc

from . import github_api

Key = tuple[str, int]  # ("owner/name", number)

_FIELDS = (  # a reply in a review thread is a review of its own, so it moves the reviews count
    "state isDraft updatedAt headRefOid baseRefName reviewDecision mergeable"
    " commits(last: 1) { nodes { commit { statusCheckRollup { state contexts(first: 100) {"
    " totalCount nodes { ... on CheckRun { status conclusion } ... on StatusContext { state } }"
    " } } } } } comments { totalCount } reviews { totalCount }"
    " reviewThreads(last: 100) { totalCount nodes { isResolved } }"
)
_BATCH = 50


def _query(repos: list[tuple[str, list[int]]]) -> str:
    parts = []
    for i, (repo, numbers) in enumerate(repos):
        owner, _, name = repo.partition("/")
        prs = " ".join(f"p{n}: pullRequest(number: {n}) {{ {_FIELDS} }}" for n in numbers)
        parts.append(
            f"r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ {prs} }}"
        )
    return "{ " + " ".join(parts) + " }"


def _batch(keys: list[Key]) -> dict[Key, str]:
    repos = [
        (repo, [n for _, n in group])
        for repo, group in itertools.groupby(sorted(keys), key=lambda key: key[0])
    ]
    data = github_api.graphql([], _query(repos), partial=True) or {}
    return {
        (repo, n): json.dumps(node, sort_keys=True)
        for i, (repo, numbers) in enumerate(repos)
        for n in numbers
        if (node := (data.get(f"r{i}") or {}).get(f"p{n}"))
    }


def fingerprints(keys: abc.Iterable[Key]) -> dict[Key, str]:
    """Each PR's fingerprint, which changes when anything a watcher reports does.

    A PR that could not be read (gone, unreadable, or the read failed) has no entry.
    """
    wanted = sorted(set(keys))
    return {
        key: value
        for start in range(0, len(wanted), _BATCH)
        for key, value in _batch(wanted[start : start + _BATCH]).items()
    }
