"""What a PR batch tells the footer: its events, and whether a comment is in it."""

import json

from lemonaid.watch import (
    batch_text,
    clip,
    delivery,
    merge_health,
    pr_activity,
    pr_comments,
    pr_events,
    roles,
)

_HEAD = "a" * 40


def _snap(head=_HEAD, comments=()):
    return pr_activity.Snapshot(
        head, "OPEN", True, "", list(comments), "main", "MERGEABLE", [], "PRIVATE"
    )


def _comment(i: str, body: str = "please fix") -> pr_comments.Comment:
    return pr_comments.Comment(i, "src/x.py:3", "sam", body)


def _stem(tmp_path):
    stem = tmp_path / "pr"
    stem.with_suffix(".reported.json").write_text("[]")
    stem.with_suffix(".merge.json").write_text(json.dumps(merge_health.Seen("", "")._asdict()))
    return stem


def test_each_comment_is_an_event(tmp_path):
    sent: list[str] = []

    pr_events.poll(_stem(tmp_path), 90, _snap(comments=[_comment("1"), _comment("2")]), sent.append)

    assert (delivery.events_in(sent[0]), delivery.has_comments(sent[0])) == (2, True)


def test_a_deferred_cut_comment_keeps_the_comment_footer_when_a_push_wakes_the_lemon(tmp_path):
    stem, sent = _stem(tmp_path), []
    wake = frozenset({roles.HEAD})

    pr_events.poll(stem, 90, _snap(comments=[_comment("1", "x" * 5000)]), sent.append, wake=wake)
    assert sent == []
    pr_events.poll(
        stem, 90, _snap(head="b" * 40, comments=[_comment("1", "x" * 5000)]), sent.append, wake=wake
    )

    footer = batch_text._closing(sent[0], "n")
    assert delivery.has_comments(sent[0]) and delivery.events_in(sent[0]) == 2
    assert "fetch one only if a cut marks it as omitted" in footer and clip.was_cut(sent[0])


def test_deferred_events_saved_as_bare_text_by_an_older_release_are_still_delivered(tmp_path):
    stem, sent = _stem(tmp_path), []
    stem.with_suffix(".dropped.json").write_text(json.dumps(["PR #90: 1 new comment(s)"]))
    stem.with_suffix(".head.json").write_text(json.dumps({"head": _HEAD, "state": "OPEN"}))

    pr_events.poll(stem, 90, _snap(head="b" * 40), sent.append, wake=frozenset({roles.HEAD}))

    assert "Seen without waking you: PR #90: 1 new comment(s)" in sent[0]
