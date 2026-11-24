"""A merged or closed PR's batch names the lemons its watcher may now end, and their Status."""

import json
import sqlite3

from lemonaid import pr_states
from lemonaid.brief import named_children
from lemonaid.launch.end import hint
from lemonaid.watch import merge_health, pr_activity, pr_events, roles

from . import shared

_HEAD = "a" * 40


def test_it_names_the_lemons_the_author_may_end_now():
    author, _ = shared.lemon("author", channel="claude:author", session="s-author")
    lead, _ = shared.lemon("lead", channel="claude:lead")
    on_it, _ = shared.lemon(
        "on-it",
        body=shared.prs(shared.PR),
        channel="codex:on-it",
        parent=author,
        session="s-author",
    )
    earlier, _ = shared.lemon(
        "earlier",
        "done",
        shared.prs(shared.OTHER_PR),
        channel="codex:earlier",
        parent=author,
        session="s-author",
    )
    shared.lemon(
        "own-place", "done", shared.prs(shared.PR), "claude:own-place", author, session="s-own"
    )
    shared.lemon(
        "still-open",
        body=shared.prs(shared.PR, shared.OTHER_PR),
        channel="codex:still-open",
        parent=author,
    )
    shared.lemon("elsewhere", body=shared.prs(shared.PR), channel="codex:elsewhere", parent=lead)
    shared.lemon(
        "unrelated", body=shared.prs(shared.OTHER_PR), channel="codex:unrelated", parent=author
    )
    pr_states.record("o/r", "12", "MERGED")

    assert hint.endable(author, shared.PR.replace("o/r", "O/R")) == {on_it: "none", earlier: "done"}
    assert sorted(hint.lines(author, shared.PR)) == sorted(
        [
            f"{on_it.split('.')[0]}, which you started, is done:"
            f" end it with `lemonaid lemon end {on_it} --expect done --expect none`",
            f"{earlier.split('.')[0]}, which you started, is done:"
            f" end it with `lemonaid lemon end {earlier}`",
        ]
    )


def _events(before: str, after: str, ending) -> list[roles.Event]:
    snap = pr_activity.Snapshot(_HEAD, after, False, "", [], "main", "MERGEABLE", [], "PRIVATE")
    return pr_events.events(
        12, snap, _HEAD, before, (False, ""), [], lambda head: False, ending=ending
    )


def test_only_a_merge_or_close_asks_for_them():
    asked: list[str] = []

    def ending() -> list[str]:
        asked.append("asked")
        return ["Bit, which you started, is done: end it with `lemonaid lemon end Bit.x`"]

    merged = _events("OPEN", "MERGED", ending)
    assert [(e.kind, e.items) for e in merged] == [(roles.STATE, 1), (roles.STATE, 0)]
    assert merged[1].text.endswith("`lemonaid lemon end Bit.x`")
    assert _events("MERGED", "OPEN", ending)[1:] == [] and _events("OPEN", "OPEN", ending) == []
    assert asked == ["asked"]


def test_a_failure_leaves_the_lines_out_and_the_merge_in(monkeypatch, tmp_path):
    def locked(conn, parent_id):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(named_children, "of", locked)
    stem = tmp_path / "pr"
    stem.with_suffix(".reported.json").write_text("[]")
    stem.with_suffix(".merge.json").write_text(json.dumps(merge_health.Seen("", "")._asdict()))
    stem.with_suffix(".head.json").write_text(json.dumps({"head": _HEAD, "state": "OPEN"}))
    snap = pr_activity.Snapshot(_HEAD, "MERGED", False, "", [], "main", "MERGEABLE", [], "PRIVATE")
    sent: list[str] = []

    pr_events.poll(
        stem, 12, snap, sent.append, ending=lambda: hint.lines("author.Lemon", shared.PR)
    )

    assert len(sent) == 1 and "PR #12 is now MERGED" in sent[0]
    assert "lemonaid lemon end" not in sent[0]
