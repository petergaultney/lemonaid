"""`watch mentions` reports direct @mentions of the user on PRs, from canned GitHub data."""

import datetime

from lemonaid.watch import (
    brief_record,
    github_api,
    mention_comments,
    mention_events,
    notifications,
    pr_poller,
    scout_pollers,
    subscriptions,
)

from .wait import shared

NOW = datetime.datetime(2026, 11, 10, 18, 0, tzinfo=datetime.UTC)
EARLIER = "2026-11-10T17:00:00Z"
URL = "https://github.com/acme/widgets/pull/7"


def _thread(reason="mention", repo="acme/widgets", number=7, updated="2026-11-10T17:55:00Z"):
    return notifications.parse_thread(
        {
            "id": "1",
            "reason": reason,
            "updated_at": updated,
            "repository": {"full_name": repo},
            "subject": {
                "type": "PullRequest",
                "url": f"https://api.github.com/repos/{repo}/pulls/{number}",
                "title": "Widgets",
            },
        }
    )


def _node(id, body, login="robin", created="2026-11-10T17:54:00Z", **extra):
    return {
        "id": id,
        "html_url": f"{URL}#{id}",
        "body": body,
        "created_at": created,
        "user": {"login": login, "type": extra.pop("type", "User")},
        **extra,
    }


def _pull(*comments, inline=(), reviews=(), body="", pr_created="2026-11-01T00:00:00Z"):
    pr = {**_node(7, body, login="lee", created=pr_created), "title": "Widgets", "html_url": URL}
    return mention_comments.parse("samlogin", pr, list(comments), list(reviews), list(inline))


def _events(cursor, pull, *, threads=None, watched=lambda repo, number: False, scope=(), now=NOW):
    return mention_events.events(
        cursor,
        [_thread()] if threads is None else threads,
        lambda repo, number, since: pull,
        watched,
        scope,
        now,
    )


def _cursor():
    return {"since": EARLIER, "floor": EARLIER, "seen": {}}


def test_direct_mentions_skip_quotes_code_teams_and_lookalikes():
    def hit(body):
        return mention_comments.mentions_login(body, "samlogin")

    assert hit("cc @SamLogin, thoughts?")
    assert hit("@samlogin")
    assert not hit("> @samlogin said this")
    assert not hit("run `@samlogin` here")
    assert not hit("```\n@samlogin\n```")
    assert not hit("@samlogin/ml-team please look")
    assert not hit("@samlogin2 and sam@samlogin.example")


def test_an_inline_review_comment_mention_is_reported_with_its_link():
    reply = _node("c1", "@samlogin why?", path="a.py", line=None, original_line=3)

    [line], cursor = _events(_cursor(), _pull(inline=[reply]))

    assert line.startswith(f'acme/widgets PR #7 "Widgets": robin mentioned you (a.py:3): {URL}#c1')
    assert line.endswith("\n> @samlogin why?")
    assert cursor["since"] == "2026-11-10T18:00:00Z" and "inline:c1" in cursor["seen"]


def test_each_mention_is_reported_once_across_overlapping_polls():
    data = _pull(_node("c1", "@samlogin ping"))
    _, cursor = _events(_cursor(), data)
    cursor["since"] = "2026-11-10T17:58:00Z"  # the next poll overlaps the comment's time

    again, _ = _events(cursor, data)

    assert again == []


def test_the_users_own_account_bots_and_old_comments_are_not_reported():
    data = _pull(
        _node("mine", "🍋 note for @samlogin", login="samlogin"),
        _node("bot", "@samlogin CI failed", login="ci", type="Bot"),
        _node("old", "@samlogin", created="2026-11-09T00:00:00Z"),
        _node("plain", "no mention here"),
    )

    assert _events(_cursor(), data)[0] == []


def test_a_new_pr_description_mention_counts_and_an_old_one_does_not():
    new = _pull(body="for @samlogin", pr_created="2026-11-10T17:56:00Z")
    old = _pull(body="for @samlogin")

    [line], _ = _events(_cursor(), new)

    assert "lee mentioned you (description)" in line
    assert _events(_cursor(), old)[0] == []


def test_the_first_poll_takes_everything_as_seen_without_reading():
    lines, cursor = mention_events.events(
        None, [_thread()], lambda *a: 1 / 0, lambda *a: False, (), NOW
    )

    assert lines == [] and cursor == {
        "since": "2026-11-10T18:00:00Z",
        "floor": "2026-11-10T18:00:00Z",
        "seen": {},
    }


def test_a_watched_pr_and_other_scopes_are_skipped_whatever_the_reason():
    data = _pull(_node("c1", "@samlogin"))

    assert _events(_cursor(), data, watched=lambda repo, number: True)[0] == []
    assert _events(_cursor(), data, scope=("org:other",))[0] == []
    assert _events(
        _cursor(), data, threads=[_thread(reason="state_change")], scope=("repo:acme/widgets",)
    )[0]


def test_an_unreadable_pr_keeps_the_cursor_for_the_next_poll():
    lines, cursor = mention_events.events(
        _cursor(), [_thread()], lambda *a: None, lambda *a: False, (), NOW
    )

    assert lines == [] and cursor["since"] == EARLIER


def test_only_a_scout_that_hears_comments_marks_a_pr_watched():
    pr_poller.interested("acme/widgets", 7, "reviewer-lemon")
    assert not pr_poller.hears_comments("acme/widgets", 7)

    pr_poller.interested("acme/widgets", 7, "author-lemon", comments=True)
    assert pr_poller.hears_comments("acme/widgets", 7)


def test_notification_pages_are_read_until_a_short_one(monkeypatch):
    pages = [[{"id": i} for i in range(50)], [{"id": 50}]]
    asked = []

    def rest(path):
        asked.append(path)
        return pages[len(asked) - 1]

    monkeypatch.setattr(notifications.github_api, "rest", rest)

    threads = notifications.fetch(EARLIER, participating=True)

    assert len(threads) == 51 and len(asked) == 2
    assert "all=true" in asked[0] and "participating=true" in asked[0]
    monkeypatch.setattr(notifications.github_api, "rest", lambda path: None)
    assert notifications.fetch(EARLIER) is None


def test_a_list_with_more_pages_than_allowed_is_a_failed_read(monkeypatch):
    monkeypatch.setattr(github_api, "rest", lambda path: [{}] * 10)

    assert github_api.rest_pages("things", {}, per_page=10, max_pages=3) is None


def test_a_mention_from_before_the_subscription_is_never_reported():
    _, first = _events(None, _pull(), now=NOW)
    before = _pull(_node("c1", "@samlogin", created="2026-11-10T17:54:00Z"))

    lines, _ = _events(first, before, now=NOW + datetime.timedelta(minutes=3))

    assert lines == []


def test_read_asks_for_comments_and_replies_updated_since_the_window(monkeypatch):
    asked = []
    reply = _node("old-thread-reply", "@samlogin here", path="a.py", line=9)

    def rest_pages(path, params, **kwargs):
        asked.append((path, params))
        return [reply] if path.endswith("pulls/7/comments") else []

    monkeypatch.setattr(github_api, "rest_pages", rest_pages)
    monkeypatch.setattr(
        github_api,
        "rest",
        lambda path: {"login": "samlogin"} if path == "user" else {"title": "Widgets"},
    )

    pull = mention_comments.read("acme/widgets", 7, EARLIER)

    assert [m.id for m in mention_comments.direct(pull, EARLIER)] == ["inline:old-thread-reply"]
    assert ("repos/acme/widgets/pulls/7/comments", {"since": EARLIER}) in asked
    assert ("repos/acme/widgets/issues/7/comments", {"since": EARLIER}) in asked


def test_a_watching_bullet_is_a_mentions_subscription(tmp_path):
    text = shared.BRIEF + "- `lemonaid watch mentions --wait --scope org:Acme --backlog`\n"

    reading = subscriptions.report(text, tmp_path)

    assert not reading.problems
    [spec] = [s for s in reading.specs if s.kind == "mentions"]
    assert spec.target == ("@me", "org:acme") and spec.backlog


def test_a_rearmed_mentions_waiter_is_the_same_watch():
    once = brief_record._identity("lemonaid watch mentions --wait --scope org:acme --once")
    plain = brief_record._identity("lemonaid watch mentions --wait --scope org:ACME")

    assert once is not None and once == plain


def test_the_scout_poller_reports_a_new_mention_once(tmp_path, monkeypatch):
    just_now = mention_events.iso(datetime.datetime.now(datetime.UTC))
    monkeypatch.setattr(
        notifications, "fetch", lambda since, participating: [_thread(updated=just_now)]
    )
    monkeypatch.setattr(
        mention_comments,
        "read",
        lambda repo, number, since: _pull(_node("c1", "@samlogin", created=just_now)),
    )
    spec = subscriptions.Subscription("mentions", ("@me",), interval=0, backlog=True)
    sent = []

    def deliver(message):
        sent.append(message)
        return True

    poll = scout_pollers.open_poller(spec, tmp_path / "cursors", "", deliver, ())
    poll()
    poll()

    assert len(sent) == 1 and "robin mentioned you" in sent[0]
