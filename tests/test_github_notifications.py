"""`lemonaid github notifications` and `watch notifications`, from canned GitHub data."""

import argparse
import json

import pytest

from lemonaid.watch import (
    brief_record,
    notification_details,
    notification_events,
    notifications,
    notifications_cli,
    subscriptions,
)

from .wait import shared


def _thread(id="1", number=7, kind="PullRequest", updated="2026-11-10T18:00:00Z", **extra):
    path = "pulls" if kind == "PullRequest" else "issues"
    return notifications.parse_thread(
        {
            "id": id,
            "reason": extra.get("reason", "comment"),
            "updated_at": updated,
            "unread": extra.get("unread", True),
            "repository": {"full_name": extra.get("repo", "acme/widgets")},
            "subject": {
                "type": kind,
                "url": f"https://api.github.com/repos/acme/widgets/{path}/{number}",
                "title": "Widgets",
            },
        }
    )


def _text(at, mine=True, body="looks good"):
    return {"createdAt": at, "viewerDidAuthor": mine, "body": body}


def _pr(*comments, state="OPEN", merged=False, reviews=()):
    return {
        "url": "https://github.com/acme/widgets/pull/7",
        "state": state,
        "merged": merged,
        "isDraft": False,
        "author": {"login": "lee"},
        "viewerLatestReview": {"state": "APPROVED", "submittedAt": "2026-11-09T00:00:00Z"},
        "commits": {"nodes": [{"commit": {"committedDate": "2026-11-08T00:00:00Z"}}]},
        "comments": {"nodes": list(comments)},
        "reviews": {"nodes": list(reviews)},
        "reviewThreads": {"nodes": []},
    }


def test_an_unsigned_comment_after_the_latest_activity_means_the_user_acted():
    d = notification_details.details(_thread(), _pr(_text("2026-11-10T18:05:00Z")))

    assert d["acted"] and d["my_last_activity_at"] == "2026-11-10T18:05:00Z"
    assert d["my_review"] == {"state": "APPROVED", "submitted_at": "2026-11-09T00:00:00Z"}
    assert d["latest_commit_at"] == "2026-11-08T00:00:00Z" and d["author"] == "lee"


def test_a_lemon_signed_comment_or_an_earlier_one_is_not_acting():
    signed = _text("2026-11-10T18:05:00Z", body="\N{LEMON} NoteBee (Author): fixed")
    earlier = _text("2026-11-10T17:00:00Z")
    theirs = _text("2026-11-10T18:06:00Z", mine=False)

    d = notification_details.details(_thread(), _pr(signed, earlier, theirs))

    assert not d["acted"] and d["my_last_activity_at"] == "2026-11-10T17:00:00Z"


def test_a_merged_pr_reads_as_closed_and_merged():
    d = notification_details.details(_thread(), _pr(state="MERGED", merged=True))

    assert d["state"] == "closed" and d["merged"]


def test_an_unreadable_subject_keeps_the_threads_own_fields():
    d = notification_details.details(_thread(), None)

    assert d["thread_id"] == "1" and "state" not in d


def test_subjects_are_read_in_batches_by_alias(monkeypatch):
    queries = []

    def graphql(fields, query, partial=False):
        queries.append(query)
        return {"t0": {"pullRequest": _pr()}, "t1": {"issue": None}}

    monkeypatch.setattr(notification_details, "_BATCH", 2)
    monkeypatch.setattr(notification_details.github_api, "graphql", graphql)
    threads = [_thread("1"), _thread("2", kind="Issue"), _thread("3"), _thread("4", kind="Release")]

    found = notification_details.describe(threads)

    assert [d["thread_id"] for d in found] == ["1", "2", "3", "4"]
    assert (
        len(queries) == 2
        and 't1: repository(owner: "acme", name: "widgets") { issue(number: 7)' in queries[0]
    )
    assert "state" in found[0] and "state" not in found[1] and "state" not in found[3]


def test_the_first_poll_takes_unread_threads_as_seen():
    lines, seen = notification_events.events(None, [_thread("1")], ())

    assert lines == [] and seen == {"1": "2026-11-10T18:00:00Z"}


def test_new_and_newly_active_threads_are_reported_and_read_ones_dropped():
    seen = {"1": "2026-11-10T18:00:00Z", "2": "2026-11-10T18:00:00Z", "3": "2026-11-10T18:00:00Z"}
    threads = [
        _thread("1"),
        _thread("2", updated="2026-11-10T19:00:00Z"),
        _thread("3", unread=False),
        _thread("4", number=9, reason="mention"),
        _thread("5", repo="other/repo"),
    ]

    lines, now = notification_events.events(seen, threads, ("org:acme",))

    assert lines == [
        '- acme/widgets#7 (comment) "Widgets" [thread 2]',
        '- acme/widgets#9 (mention) "Widgets" [thread 4]',
    ]
    assert sorted(now) == ["1", "2", "4"]


def test_backlog_reports_what_is_already_unread():
    lines, _ = notification_events.events(None, [_thread("1")], (), backlog=True)

    assert len(lines) == 1


def test_poll_batches_the_lines_and_saves_the_cursor(tmp_path, monkeypatch):
    monkeypatch.setattr(notifications, "fetch", lambda unread: [_thread("1"), _thread("2")])
    stem = notification_events.state_stem(tmp_path, (), "")
    got: list[str] = []

    assert notification_events.poll(stem, (), got.append, backlog=True)
    assert not notification_events.poll(stem, (), got.append)
    assert len(got) == 1 and got[0].startswith("2 GitHub notification thread(s)")
    monkeypatch.setattr(notifications, "fetch", lambda unread: None)
    assert notification_events.poll(stem, (), got.append) is None


def test_read_reports_each_thread_and_fails_if_any_did(monkeypatch, capsys):
    monkeypatch.setattr(notifications, "mark_read", lambda thread_id: thread_id != "2")

    code = notifications_cli._read(argparse.Namespace(thread_ids=["1", "2"]))

    assert code == 1 and capsys.readouterr().out.splitlines() == ["read 1", "failed 2"]


def test_list_prints_json_for_lemons(monkeypatch, capsys):
    monkeypatch.setattr(notifications, "fetch", lambda unread: [_thread("1")])
    monkeypatch.setattr(notification_details.github_api, "graphql", lambda *a, **k: {})

    assert notifications_cli._list(argparse.Namespace(scope=[], json=True)) == 0
    assert json.loads(capsys.readouterr().out)[0]["thread_id"] == "1"


def test_mark_read_patches_the_thread(monkeypatch):
    sent = []
    monkeypatch.setattr(
        notifications.github_api,
        "rest_send",
        lambda path, method: sent.append((method, path)) or True,
    )

    assert notifications.mark_read("42")
    assert sent == [("PATCH", "notifications/threads/42")]


def test_a_watching_bullet_is_a_notifications_subscription(tmp_path):
    text = shared.BRIEF + "- `lemonaid watch notifications --wait --every 60 --scope org:Acme`\n"

    reading = subscriptions.report(text, tmp_path)

    assert not reading.problems
    [spec] = [s for s in reading.specs if s.kind == "notifications"]
    assert spec.target == ("@me", "org:acme") and spec.interval == 3600


def test_a_rearmed_notifications_waiter_is_the_same_watch():
    once = brief_record._identity("lemonaid watch notifications --wait --once")
    plain = brief_record._identity("lemonaid watch notifications --wait --every 10")

    assert once is not None and once == plain


@pytest.mark.parametrize("command", ["list", "show 1", "read 1"])
def test_the_github_notifications_commands_parse(command):
    parser = argparse.ArgumentParser()
    notifications_cli.setup_parser(parser.add_subparsers())

    assert parser.parse_args(["github", "notifications", *command.split()]).func


def test_a_pending_inline_comment_is_not_acting():
    node = _pr()
    node["reviewThreads"]["nodes"] = [
        {"comments": {"nodes": [{**_text("2026-11-10T18:05:00Z"), "state": "PENDING"}]}}
    ]

    assert not notification_details.details(_thread(reason="review_requested"), node)["acted"]
    assert "comments(last: 5) { nodes { createdAt viewerDidAuthor body state } }" in (
        notification_details._query([_thread()])
    )


def test_any_lemon_marked_comment_is_not_acting_even_without_a_role():
    node = _pr(_text("2026-11-10T18:05:00Z", body="\N{LEMON} Codex: fixed"))

    assert not notification_details.details(_thread(reason="mention"), node)["acted"]
