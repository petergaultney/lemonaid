"""`watch repo` reports opened, ready, labeled and closed PRs from canned GraphQL data."""

import subprocess

from lemonaid.watch import repo_activity, repo_cli, repo_events, subscriptions

from .wait import shared

REPO = "acme/widgets"


def _pr(number=1, *, draft=False, state="OPEN", labels=(), author="sam", head="a" * 40):
    return repo_activity.PullRequest(
        number, f"Title {number}", author, f"feat/{number}", head, draft, state, tuple(labels)
    )


def _seen(*prs):
    return repo_events.events(REPO, None, prs)[1]


def test_the_first_poll_reports_nothing_and_takes_open_prs_as_seen():
    lines, seen = repo_events.events(
        REPO, None, [_pr(1), _pr(2, draft=True), _pr(3, state="MERGED")]
    )

    assert lines == []
    assert sorted(seen) == ["1", "2"]


def test_a_new_ready_pr_names_its_number_title_author_and_head():
    [line], _ = repo_events.events(REPO, _seen(), [_pr(7)])

    assert line == 'acme/widgets PR #7 "Title 7" by sam (feat/7) was opened ready for review'


def test_a_new_draft_is_silent_until_it_is_marked_ready():
    lines, seen = repo_events.events(REPO, _seen(), [_pr(7, draft=True)])
    ready, _ = repo_events.events(REPO, seen, [_pr(7)])

    assert lines == []
    assert ready == ['acme/widgets PR #7 "Title 7" by sam (feat/7) is now ready for review']


def test_a_label_filter_reports_only_prs_carrying_one_of_the_labels():
    seen = _seen(_pr(1), _pr(2))
    prs = [_pr(1, labels=["Needs-Review"]), _pr(2, labels=["wip"]), _pr(3, labels=["other"])]

    lines, _ = repo_events.events(REPO, seen, prs, labels=["needs-review"])

    assert lines == ['acme/widgets PR #1 "Title 1" by sam (feat/1) got label needs-review']


def test_a_pr_opened_without_a_watched_label_reports_when_it_gains_one():
    lines, seen = repo_events.events(REPO, _seen(), [_pr(4)], labels=["x"])
    gained, _ = repo_events.events(REPO, seen, [_pr(4, labels=["x"])], labels=["x"])

    assert lines == []
    assert len(gained) == 1 and "got label x" in gained[0]


def test_excluded_authors_are_skipped_whatever_the_case():
    lines, _ = repo_events.events(
        REPO, _seen(), [_pr(5, author="Bot-User")], exclude_authors=["bot-user"]
    )

    assert lines == []


def test_a_head_moving_is_reported_only_with_pushes():
    seen = _seen(_pr(1))
    moved = [_pr(1, head="b" * 40)]

    assert repo_events.events(REPO, seen, moved)[0] == []
    [line], _ = repo_events.events(REPO, seen, moved, pushes=True)
    assert line.endswith("head moved aaaaaaaaaa -> bbbbbbbbbb")


def test_a_seen_pr_closed_or_merged_is_reported_once():
    seen = _seen(_pr(1), _pr(2))

    lines, now = repo_events.events(REPO, seen, [_pr(1, state="MERGED"), _pr(9, state="CLOSED")])
    again, _ = repo_events.events(REPO, now, [_pr(1, state="MERGED")])

    assert lines == ['acme/widgets PR #1 "Title 1" by sam (feat/1) was merged']
    assert again == []
    assert sorted(now) == ["2"]


def test_poll_saves_the_cursor_only_once_delivery_returns(tmp_path):
    stem = repo_events.state_stem(tmp_path, REPO, "")
    repo_events.poll(stem, REPO, [_pr(1)], lambda message: None)
    got: list[str] = []

    assert repo_events.poll(stem, REPO, [_pr(1), _pr(2)], got.append)
    assert not repo_events.poll(stem, REPO, [_pr(1), _pr(2)], got.append)
    assert len(got) == 1 and "PR #2" in got[0]


def test_parse_reads_open_pages_then_closed_prs():
    node = {
        "number": 3,
        "title": "t",
        "isDraft": False,
        "state": "OPEN",
        "headRefName": "b",
        "headRefOid": "c" * 40,
        "author": None,
        "labels": {"nodes": [{"name": "x"}]},
    }
    closed = {**node, "number": 4, "state": "MERGED"}
    pages = [{"open": {"nodes": [node]}, "closed": {"nodes": [closed]}}, {"open": {"nodes": []}}]

    prs = repo_activity.parse(pages)

    assert [(p.number, p.state, p.author, p.labels) for p in prs] == [
        (3, "OPEN", "ghost", ("x",)),
        (4, "MERGED", "ghost", ("x",)),
    ]


def test_a_watching_line_is_read_as_a_repo_subscription(tmp_path):
    spec = subscriptions._parse(
        "lemonaid watch repo --wait acme/widgets --label a --label b --exclude-author sam --once",
        "p.Wordy",
        "Author (Wordy)",
        tmp_path,
    )

    assert spec.kind == "repo" and spec.target == ("acme/widgets",)
    assert spec.labels == ("a", "b") and spec.exclude_authors == ("sam",)


def test_the_repo_argument_must_be_owner_slash_name():
    try:
        repo_cli._repo("widgets")
    except Exception as error:
        assert "owner/name" in str(error)
    else:
        raise AssertionError("accepted a bare name")


def test_a_watching_bullet_with_once_is_a_repo_subscription(tmp_path):
    text = shared.BRIEF + "- `lemonaid watch repo --wait acme/widgets --once`\n"

    reading = subscriptions.report(text, tmp_path)

    assert not reading.problems
    assert [s.target for s in reading.specs if s.kind == "repo"] == [("acme/widgets",)]


def test_a_gh_timeout_is_a_failed_fetch_not_an_exception(monkeypatch):
    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired("gh", 30)

    monkeypatch.setattr(subprocess, "run", hang)

    assert repo_activity.fetch(REPO) is None
