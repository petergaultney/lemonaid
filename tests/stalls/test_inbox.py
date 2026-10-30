import time

import pytest

from lemonaid.brief import attached, identity, store
from lemonaid.config import load_config
from lemonaid.inbox import db, presence, view
from lemonaid.inbox.tui.rows.brief_cards import BriefCache
from lemonaid.stalls import inbox
from lemonaid.watch import cursors, pr_activity, pr_poller

from .shared import KEY, snap

URL = "https://github.com/acme/widgets/pull/238"


def _lemon(conn, brief_id: str) -> str:
    """A visible lemon whose brief lists the PR, as both authors and reviewers do."""
    row = db.add(conn, f"claude:{brief_id}", "a message", brief_id, {"cwd": "/tmp"})
    path = store.briefs_dir() / f"2026-10-21-{brief_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Widgets 238\n\nBrief-ID: {brief_id}.SaltyEbb\n\n## Now\n\n## PRs\n\n"
        f"| Work | PR | Review |\n|---|---|---|\n| Widgets | [widgets#238]({URL}) | |\n"
    )
    identity.ensure(conn, path)
    attached.attach(conn, row.channel, path)
    return row.channel


@pytest.mark.parametrize(
    ("brief_id", "stuck"),
    [
        ("review-widgets-238", ""),
        ("widgets-238", "stuck 1h: Your move on #238; its brief should say `merge`"),
    ],
)
def test_the_stall_check_knows_a_visible_reviewer_by_its_brief_id(brief_id, stuck):
    tracker = inbox.Tracker()
    with db.connect() as conn:
        channel = _lemon(conn, brief_id)
        now = time.time()
        tracker.store(KEY, snap(decision="APPROVED"), now)
        active = view.ordered_active(conn, None, BriefCache(), presence.Probe(), False, now)
        marked = tracker.mark(conn, active, load_config(), now + 3600)

    assert active.hidden_briefs == set()
    assert marked.cards[channel].stuck == stuck


def test_a_pr_the_scout_host_keeps_is_not_read_from_github_again(monkeypatch):
    reads = []
    monkeypatch.setattr(pr_activity, "read", lambda repo, number: reads.append(number))
    repository = {
        "pullRequest": {
            "headRefOid": "abc1234def",
            "baseRefName": "main",
            "state": "OPEN",
            "isDraft": False,
            "reviewDecision": "APPROVED",
            "mergeable": "MERGEABLE",
            "commits": {"nodes": [{"commit": {"oid": "abc1234def", "statusCheckRollup": None}}]},
            "reviewThreads": {"nodes": []},
            "reviews": {"nodes": []},
            "comments": {"nodes": []},
        },
    }
    cursors.write_json(
        pr_poller._snapshot_path(KEY[0], int(KEY[1])),
        {"fingerprint": "f", "fetched": time.time(), "repository": repository},
    )

    found = inbox.fetch(KEY)

    assert found is not None and found.decision == "APPROVED" and reads == []
