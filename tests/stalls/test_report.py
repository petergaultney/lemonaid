from pathlib import Path

from lemonaid.stalls import pulls, report

from .shared import KEY, comment, lemon, snap

NOW = 10_000.0
IDLE = NOW - 45 * 60


def _pull(tmp_path: Path, doc_text: str = "", **kw) -> pulls.Pull:
    doc = tmp_path / "doc.md"
    doc.write_text(doc_text)
    author = kw.pop("author", lemon("a", tmp_path / "a.md", name="Mot", since=IDLE))
    reviewer = kw.pop(
        "reviewer", lemon("r", tmp_path / "r.md", name="Salty", since=IDLE, reviewer=True)
    )
    return pulls.Pull(KEY, author, reviewer, doc, kw.pop("reviewed_head", ""))


def _find(pull: pulls.Pull, snapshot) -> list[report.Stall]:
    return report.find([pull], {KEY: snapshot}, NOW, 15)


def test_idle_reviewer_after_author_reply_is_stuck(tmp_path: Path) -> None:
    [stall] = _find(_pull(tmp_path, comment("Author (Mot)")), snap())
    assert (stall.channel, stall.line) == ("r", "stuck 45m: reviewer's move on #238")


def test_idle_author_after_reviewer_comment_is_stuck(tmp_path: Path) -> None:
    [stall] = _find(_pull(tmp_path, comment("Reviewer (Salty)")), snap())
    assert stall.channel == "a"


def test_working_lemon_is_not_stuck(tmp_path: Path) -> None:
    reviewer = lemon("r", tmp_path / "r.md", name="Salty", mid_turn=True, since=IDLE, reviewer=True)
    assert _find(_pull(tmp_path, comment("Author (Mot)"), reviewer=reviewer), snap()) == []


def test_idle_under_the_threshold_is_not_stuck(tmp_path: Path) -> None:
    reviewer = lemon("r", tmp_path / "r.md", name="Salty", since=NOW - 60, reviewer=True)
    assert _find(_pull(tmp_path, comment("Author (Mot)"), reviewer=reviewer), snap()) == []


def test_a_brief_that_says_why_silences_the_pr(tmp_path: Path) -> None:
    author = lemon("a", tmp_path / "a.md", name="Mot", status="blocked", since=IDLE)
    assert _find(_pull(tmp_path, comment("Author (Mot)"), author=author), snap()) == []


def test_ready_pr_flags_an_author_who_did_not_say_merge(tmp_path: Path) -> None:
    [stall] = _find(_pull(tmp_path), snap(decision="APPROVED"))
    assert (stall.channel, stall.line) == (
        "a",
        "stuck 45m: Peter's move on #238; its brief should say `merge`",
    )


def test_merged_pr_flags_each_brief_still_listing_it(tmp_path: Path) -> None:
    stalls = _find(_pull(tmp_path), snap(state="MERGED"))
    assert [s.channel for s in stalls] == ["a", "r"]
    assert stalls[0].line == "stuck 45m: #238 is merged but its brief isn't done"


def test_merged_pr_flags_even_a_brief_saying_merge(tmp_path: Path) -> None:
    author = lemon("a", tmp_path / "a.md", name="Mot", status="merge", since=IDLE)
    assert [s.channel for s in _find(_pull(tmp_path, author=author), snap(state="CLOSED"))] == [
        "a",
        "r",
    ]


def test_pr_without_a_snapshot_is_never_stuck(tmp_path: Path) -> None:
    assert _find(_pull(tmp_path, comment("Author (Mot)")), None) == []
