from pathlib import Path

from lemonaid.stalls import pulls
from lemonaid.watch import pr_activity

KEY = ("acme/widgets", "238")


def snap(
    *,
    state: str = "OPEN",
    head: str = "abc1234def",
    decision: str = "",
    draft: bool = False,
    mergeable: str = "MERGEABLE",
    outcome: str = "passed",
) -> pr_activity.Snapshot:
    return pr_activity.Snapshot(
        head,
        state,
        draft,
        decision,
        [],
        "main",
        mergeable,
        [pr_activity.Check("ci", True, outcome)],
    )


def lemon(
    channel: str,
    path: Path,
    *,
    name: str = "",
    status: str = "",
    mid_turn: bool = False,
    since: float = 0.0,
    reviewer: bool = False,
) -> pulls.Lemon:
    return pulls.Lemon(channel, path, name or channel, status, mid_turn, since, reviewer)


def comment(author: str, text: str = "x") -> str:
    return f'{{=={text}==}}{{{{author="{author}">>{text}<<}}}}'
