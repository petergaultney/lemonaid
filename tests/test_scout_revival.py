"""The live inbox restarts the push scout of a Claude lemon it marks deaf, at most once a minute."""

from lemonaid.brief import store
from lemonaid.inbox import scout_revival
from lemonaid.watch import push_scout


def test_only_claude_channels_are_due_and_each_waits_between_tries():
    revival = scout_revival.Revival()

    assert revival.due(["claude:aaaa1111", "codex:thread"], now=100.0) == ["claude:aaaa1111"]
    assert revival.due(["claude:aaaa1111"], now=130.0) == []
    assert revival.due(["claude:aaaa1111"], now=100.0 + scout_revival.RETRY_SECONDS) == [
        "claude:aaaa1111"
    ]


def test_revive_starts_the_scout_for_the_brief_s_lemon(monkeypatch):
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text("# task\n\nBrief-ID: task.IndexElf\n")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        push_scout,
        "ensure",
        lambda session_id, lemon_id: calls.append((session_id, lemon_id)) or True,
    )

    assert scout_revival.revive("claude:aaaa1111", path)
    assert calls == [("aaaa1111", "task.IndexElf")]
