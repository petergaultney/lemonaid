from lemonaid.watch import pr_reviewers


def _user(login: str) -> dict[str, str]:
    return {"__typename": "User", "login": login}


def test_the_author_isnt_an_assignee_and_each_reviewers_latest_verdict_decides():
    pr = {
        "author": {"login": "pat"},
        "assignees": {"nodes": [{"login": "kim"}, {"login": "pat"}]},
        "reviews": {
            "nodes": [
                {"state": "APPROVED", "author": _user("sam")},
                {"state": "CHANGES_REQUESTED", "author": _user("ann")},
                {"state": "APPROVED", "author": _user("ann")},
                {"state": "APPROVED", "author": _user("lee")},
                {"state": "COMMENTED", "author": _user("lee")},
                {"state": "APPROVED", "author": _user("joe")},
                {"state": "DISMISSED", "author": _user("joe")},
                {"state": "APPROVED", "author": {"__typename": "Bot", "login": "bot"}},
                {"state": "APPROVED", "author": None},
            ]
        },
    }

    assert pr_reviewers.assigned(pr) == ("kim",)
    assert pr_reviewers.verdicts(pr, "APPROVED") == ("sam", "ann", "lee")
    assert pr_reviewers.verdicts(pr, "CHANGES_REQUESTED") == ()


def test_a_reviewer_still_requesting_changes_is_kept_and_a_cut_off_history_is_unknown():
    kim = {"state": "CHANGES_REQUESTED", "author": _user("kim")}
    sam = {"state": "APPROVED", "author": _user("sam")}
    pr = {"reviews": {"nodes": [kim, sam]}}
    full = {"reviews": {"nodes": [sam] * 49 + [kim]}}

    assert pr_reviewers.verdicts(pr, "CHANGES_REQUESTED") == ("kim",)
    assert pr_reviewers.verdicts(full, "APPROVED") is None


def test_a_snapshot_without_assignees_leaves_them_unknown():
    assert pr_reviewers.assigned({"reviews": {"nodes": []}}) is None


def test_the_users_own_latest_verdict_is_read_and_absent_from_an_old_snapshot():
    assert pr_reviewers.user_verdict({"viewerLatestReview": {"state": "APPROVED"}}) == "APPROVED"
    assert pr_reviewers.user_verdict({"viewerLatestReview": None}) == ""
    assert pr_reviewers.user_verdict({}) is None
