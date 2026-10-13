from pathlib import Path

from lemonaid.stalls import pulls

from .shared import lemon

URL = "https://github.com/acme/widgets/pull/238"


def _brief(path: Path, body: str) -> Path:
    path.write_text(f"# Work\n\n## Now\n\n### PRs\n\n{body}\n")
    return path


def test_author_row_pairs_with_the_reviewer_that_mentions_the_pr(tmp_path: Path) -> None:
    doc_url = "obsidian://open?vault=vault&file=pr-reviews%2F238"
    author = lemon(
        "a",
        _brief(
            tmp_path / "a.md",
            f"| Work | PR | Review |\n|---|---|---|\n| x | [w#238]({URL}) | [d]({doc_url}) |",
        ),
    )
    (tmp_path / "r.md").write_text(
        f"Review {URL}\n\n## Waiters\n\n- `lemonaid watch pr --wait 238 --head abc1234 --me X`\n"
    )
    reviewer = lemon("r", tmp_path / "r.md", reviewer=True)
    [pull] = pulls.find([author, reviewer], [tmp_path / "vault"])
    assert pull.key == ("acme/widgets", "238")
    assert pull.reviewer == reviewer
    assert pull.reviewed_head == "abc1234"
    assert pull.doc == tmp_path / "vault" / "pr-reviews/238.md"


def test_done_briefs_are_left_out(tmp_path: Path) -> None:
    table = f"| Work | PR | Review |\n|---|---|---|\n| x | [w#238]({URL}) | |"
    author = lemon("a", _brief(tmp_path / "a.md", table), status="done")
    assert pulls.find([author], []) == []
