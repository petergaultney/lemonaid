import math

from lemonaid.tasks.checker import protocol
from lemonaid.tasks.inspection import memory


def _input(now: str, observed: str, value: str = "idle") -> str:
    return protocol.render(
        [
            ("context", "now", now),
            ("fact", "lemon", "Work.alpha", "activity", value, observed, "known"),
        ]
    )


def test_a_fingerprint_ignores_when_things_were_seen_but_not_what_was():
    seen = memory.fingerprint(_input("2026-11-02T10:00:00Z", "2026-11-02T10:00:00Z"))

    assert seen == memory.fingerprint(_input("2026-11-02T11:00:00Z", "2026-11-02T11:00:00Z"))
    assert seen != memory.fingerprint(
        _input("2026-11-02T10:00:00Z", "2026-11-02T10:00:00Z", "active")
    )


def test_findings_hold_until_their_earliest_recheck_or_wait():
    remembered = memory.new()
    text = _input("2026-11-02T10:00:00Z", "2026-11-02T10:00:00Z")
    due = "2026-11-02T10:05:00Z"

    memory.remember(remembered, "t1", text, [("ok", "t1", "x"), ("recheck", "t1", due)])

    assert memory.unchanged(remembered, "t1", text, 1_793_000_000.0)
    assert not memory.unchanged(remembered, "t1", text, 1_793_000_000.0 + 10 * 86400)
    memory.remember(remembered, "t2", text, [("ok", "t2", "x")])
    assert remembered.judged["t2"][1] == math.inf
