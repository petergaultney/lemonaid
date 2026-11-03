"""Which people are assigned to a PR, and which have approved it.

Only people count: the PR's author among its assignees, and a review given by a bot, are
left out.
"""

QUERY = """
      viewerDidAuthor
      author { login }
      assignees(first: 20) { nodes { login } }
"""

_VERDICTS = frozenset({"APPROVED", "CHANGES_REQUESTED", "DISMISSED"})

_FETCHED = 50  # pr_activity's `reviews(last: 50)`


def assigned(pr: dict) -> tuple[str, ...] | None:
    """None for a snapshot cached before the query asked for assignees."""
    if "assignees" not in pr:
        return None

    author = (pr.get("author") or {}).get("login")
    return tuple(node["login"] for node in pr["assignees"]["nodes"] if node["login"] != author)


def verdicts(pr: dict, verdict: str) -> tuple[str, ...] | None:
    """People whose latest review verdict is *verdict*; None when the fetched reviews may
    not reach back to the first, so an earlier verdict could be missing."""
    nodes = pr["reviews"]["nodes"]
    if len(nodes) >= _FETCHED:
        return None

    latest = {
        review["author"]["login"]: review["state"]
        for review in nodes
        if review["state"] in _VERDICTS
        and review["author"]
        and review["author"]["__typename"] == "User"
    }
    return tuple(who for who, state in latest.items() if state == verdict)
