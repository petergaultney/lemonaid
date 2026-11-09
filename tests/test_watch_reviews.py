"""`watch reviews` reports PRs newly requesting the user's review, or assigned, from canned data."""

import os
import subprocess

from lemonaid.watch import (
    brief_record,
    review_events,
    review_requests,
    scout_pollers,
    subscriptions,
)

from .wait import shared

URL = "https://github.com/acme/widgets/pull/{}"


def _pr(number=1, *, requested=True, assigned=False):
    return review_requests.PullRequest(
        URL.format(number), "acme/widgets", number, f"Title {number}", "sam", requested, assigned
    )


def _seen(*prs):
    return review_events.events(None, prs)[1]


def _node(number):
    return {
        "url": URL.format(number),
        "number": number,
        "title": f"Title {number}",
        "author": None,
        "repository": {"nameWithOwner": "acme/widgets"},
    }


def test_the_first_poll_takes_current_requests_as_seen():
    lines, seen = review_events.events(None, [_pr(1), _pr(2, requested=False, assigned=True)])

    assert lines == []
    assert sorted(seen) == [URL.format(1), URL.format(2)]


def test_backlog_reports_current_requests_on_the_first_poll():
    lines, _ = review_events.events(None, [_pr(1)], backlog=True)

    assert lines == [
        'acme/widgets PR #1 "Title 1" by sam requests your review: '
        "https://github.com/acme/widgets/pull/1"
    ]


def test_a_new_request_and_a_new_assignment_are_each_reported_once():
    lines, seen = review_events.events(_seen(), [_pr(1), _pr(2, requested=False, assigned=True)])
    again, _ = review_events.events(seen, [_pr(1), _pr(2, requested=False, assigned=True)])

    assert [line.split(" by sam ")[1].split(":")[0] for line in lines] == [
        "requests your review",
        "is assigned to you",
    ]
    assert again == []


def test_assignment_mirrored_onto_a_requested_pr_is_not_reported_again():
    seen = _seen(_pr(1))

    lines, _ = review_events.events(seen, [_pr(1, assigned=True)])

    assert lines == []


def test_a_request_renewed_after_a_review_is_reported_again():
    reviewed = _seen(_pr(1, requested=False, assigned=True))

    [line], _ = review_events.events(reviewed, [_pr(1, assigned=True)])

    assert "requests your review" in line


def test_a_pr_that_leaves_and_returns_is_reported_again():
    _, gone = review_events.events(_seen(_pr(1)), [])

    [line], _ = review_events.events(gone, [_pr(1)])

    assert "PR #1" in line


def test_poll_saves_the_cursor_only_once_delivery_returns(tmp_path):
    stem = review_events.state_stem(tmp_path, (), "")
    review_events.poll(stem, [_pr(1)], lambda message: None)
    got: list[str] = []

    assert review_events.poll(stem, [_pr(1), _pr(2)], got.append)
    assert not review_events.poll(stem, [_pr(1), _pr(2)], got.append)
    assert len(got) == 1 and "PR #2" in got[0]


def test_parse_merges_the_two_searches_by_url():
    data = {"requested": {"nodes": [_node(1), {}]}, "assigned": {"nodes": [_node(1), _node(2)]}}

    prs = review_requests.parse(data)

    assert [(p.number, p.author, p.requested, p.assigned) for p in prs] == [
        (1, "ghost", True, True),
        (2, "ghost", False, True),
    ]


def test_the_scope_narrows_both_searches():
    requested, assigned = review_requests.queries(["org:acme"])

    assert requested == "user-review-requested:@me is:open is:pr archived:false org:acme"
    assert assigned == "assignee:@me is:open is:pr archived:false org:acme"


def test_one_read_serves_every_waiter_within_the_interval(monkeypatch):
    calls = []

    def graphql(fields, query):
        calls.append(fields)
        return {"requested": {"nodes": [_node(1)]}, "assigned": {"nodes": []}}

    monkeypatch.setattr(review_requests.github_api, "graphql", graphql)

    first = review_requests.fetch(("org:acme",), 60)
    second = review_requests.fetch(("org:acme",), 60)
    review_requests.fetch(("org:acme",), 0)

    assert first == second and len(first) == 1
    assert len(calls) == 2


def test_an_unchanged_read_after_expiry_renews_the_snapshot_and_a_failure_does_not(monkeypatch):
    calls, answers = [], [{"requested": {"nodes": []}, "assigned": {"nodes": []}}] * 2 + [None]

    def graphql(fields, query):
        calls.append(fields)
        return answers[len(calls) - 1]

    monkeypatch.setattr(review_requests.github_api, "graphql", graphql)
    path = review_requests._snapshot_path(())

    review_requests.fetch((), 60)
    os.utime(path, (1, 1))
    review_requests.fetch((), 60)
    review_requests.fetch((), 60)
    os.utime(path, (1, 1))

    assert len(calls) == 2
    assert review_requests.fetch((), 60) is None
    assert path.stat().st_mtime == 1


def test_a_gh_timeout_is_a_failed_fetch_not_an_exception(monkeypatch):
    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired("gh", 30)

    monkeypatch.setattr(subprocess, "run", hang)

    assert review_requests.fetch((), 60) is None


def test_a_watching_bullet_is_a_reviews_subscription(tmp_path):
    text = (
        shared.BRIEF
        + "- `lemonaid watch reviews --wait --scope org:Acme --scope repo:o/r --backlog`\n"
    )

    reading = subscriptions.report(text, tmp_path)

    assert not reading.problems
    [spec] = [s for s in reading.specs if s.kind == "reviews"]
    assert spec.target == ("@me", "org:acme", "repo:o/r")
    assert spec.backlog and spec.interval == 180


def test_a_bad_scope_is_a_problem(tmp_path):
    text = shared.BRIEF + "- `lemonaid watch reviews --wait --scope acme`\n"

    assert subscriptions.report(text, tmp_path).problems


def test_a_rearmed_reviews_waiter_is_the_same_watch():
    once = brief_record._identity("lemonaid watch reviews --wait --scope org:acme --once")
    plain = brief_record._identity("lemonaid watch reviews --wait --scope org:ACME")

    assert once is not None and once == plain


def test_the_scout_poller_reports_a_new_request(tmp_path, monkeypatch):
    found = [[_pr(1)], [_pr(1), _pr(2)]]
    monkeypatch.setattr(review_requests, "fetch", lambda scope, max_age: found.pop(0))
    spec = subscriptions.Subscription("reviews", ("@me", "org:acme"), interval=60)
    sent = []

    def deliver(message):
        sent.append(message)
        return True

    poll = scout_pollers.open_poller(spec, tmp_path / "cursors", "", deliver, ())
    poll()
    poll()

    assert len(sent) == 1 and "PR #2" in sent[0]
