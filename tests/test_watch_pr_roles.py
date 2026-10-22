from lemonaid.watch import pr_roles

_ROW = "| Work | [r#12](https://github.com/o/r/pull/12) | {review} |"


def _brief(header="", review="", waiter=""):
    return "\n".join(
        [
            "# task",
            "",
            "Brief-ID: task.IndexElf",
            *([header] if header else []),
            "",
            "## PRs",
            "",
            "| Work | PR | Review |",
            "|---|---|---|",
            _ROW.format(review=review),
            "",
            "## Watching",
            "",
            *([waiter] if waiter else []),
        ]
    )


def test_a_childs_own_pr_counts_and_its_review_does_not(tmp_path):
    doc = tmp_path / "docket.md"
    signed = "- `lemonaid watch pr --wait https://github.com/o/r/pull/12 --me 'Reviewer (X)'`"

    assert pr_roles._authored(_brief(), tmp_path, ()) == {("o/r", "12")}
    assert pr_roles._authored(_brief(waiter=signed), tmp_path, ()) == set()
    assert pr_roles._authored(_brief(f"Output-Doc: {doc}", f"[doc]({doc})"), tmp_path, ()) == set()
