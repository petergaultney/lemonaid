from lemonaid.stalls import move

from .shared import snap


def _whose(s, author=False, reviewer=False, head="") -> str:
    return move.whose(s, author_wrote_last=author, reviewer_wrote_last=reviewer, reviewed_head=head)


def test_merged_pr_is_its_briefs_move() -> None:
    assert _whose(snap(state="MERGED")) == "holder"


def test_author_reply_is_the_reviewers_move() -> None:
    assert _whose(snap(), author=True) == "reviewer"


def test_push_since_reviewed_head_is_the_reviewers_move() -> None:
    assert _whose(snap(head="bbbbbbb1"), head="aaaaaaa") == "reviewer"
    assert _whose(snap(head="aaaaaaa1"), head="aaaaaaa") == ""


def test_reviewer_comment_is_the_authors_move() -> None:
    assert _whose(snap(), reviewer=True) == "author"


def test_reviewer_comment_after_a_push_is_still_the_reviewers_move() -> None:
    assert _whose(snap(head="bbbbbbb1"), reviewer=True, head="aaaaaaa") == "reviewer"


def test_approved_green_mergeable_is_users_move() -> None:
    assert _whose(snap(decision="APPROVED")) == "user"
    assert _whose(snap(decision="APPROVED", outcome="pending")) == ""
    assert _whose(snap(decision="APPROVED", mergeable="CONFLICTING")) == ""
    assert _whose(snap(decision="APPROVED", draft=True)) == ""


def test_merge_outranks_the_reviewers_last_acknowledgement() -> None:
    assert _whose(snap(decision="APPROVED"), reviewer=True) == "user"


def test_approved_pr_with_ci_running_is_nobodys_move() -> None:
    assert _whose(snap(decision="APPROVED", outcome="pending"), reviewer=True) == ""
    assert _whose(snap(decision="APPROVED", outcome="failed"), reviewer=True) == "author"
