from lemonaid.brief import doc_table
from lemonaid.watch import subscriptions

from .wait import shared


def test_subscription_parser_deduplicates_tables_and_requires_no_shell(tmp_path):
    pr = "https://github.com/o/r/pull/12"
    text = shared.BRIEF.replace(
        "## Watching",
        "## Now\n\n### PRs\n\n| Work | PR | Review |\n|---|---|---|\n| Work | [r#12]("
        + pr
        + ") | |\n\n## Watching",
    )
    text += f'- `lemonaid watch pr --wait {pr} --me "Reviewer (IndexElf)"`\n'
    specs = subscriptions.read(text, tmp_path)
    prs = [s for s in specs if s.kind == "pr"]
    assert len(prs) == 1 and prs[0].comments and not prs[0].ci
    assert prs[0].role == "reviewer"
    assert prs[0].me == "Reviewer (IndexElf)"
    reading = subscriptions.report(shared.BRIEF + "- `sh arbitrary-script`\n", tmp_path)
    assert reading.problems
    assert [spec.kind for spec in reading.specs] == ["briefs"]


def test_bad_legacy_lines_do_not_hide_tables_files_or_children(tmp_path):
    doc = tmp_path / "docket.md"
    text = f"""# Legacy task

## Now

### PRs

| Work | PR | Review |
|---|---|---|
| Work | [r#12](https://github.com/o/r/pull/12) | [docket](obsidian://open?vault={tmp_path.name}&file=docket) |

## Limits

## Limits

## Waiters
- `sh /tmp/custom.sh`
- `lemonaid watch pr --wait 12 --repo o/r --head <head SHA>`
- `lemonaid watch file --wait {tmp_path / "source"}`
"""
    reading = subscriptions.report(text, tmp_path, owner="task.IndexElf", vaults=(tmp_path,))
    assert len(reading.problems) == 1
    assert {s.key for s in reading.specs} == {
        ("pr", ("o/r", "12")),
        ("doc", (str(doc),)),
        ("file", (str(tmp_path / "source"),)),
        ("briefs", ("task.IndexElf",)),
    }
    assert next(s for s in reading.specs if s.kind == "doc").edits is True
    assert next(s for s in reading.specs if s.kind == "pr").head == ""
    assert next(s for s in reading.specs if s.kind == "briefs").to == frozenset({"merge", "done"})


def test_a_backticked_watch_command_ignores_the_note_after_it(tmp_path):
    text = "# task\n\nBrief-ID: task.IndexElf\n\n## Watching\n- `lemonaid watch doc --wait /vault/review.md --once` (background task, rearmed after each event)\n"
    reading = subscriptions.report(text, tmp_path)
    assert not reading.problems
    assert any(
        spec.kind == "doc" and spec.target == ("/vault/review.md",) for spec in reading.specs
    )


def test_docs_watch_enum_selects_the_document_events(tmp_path):
    for mode in doc_table.Watch:
        text = doc_table.add(
            "# task\n\nBrief-ID: task.IndexElf\n", tmp_path / "design.md", "Design", watch=mode
        )
        spec = next(spec for spec in subscriptions.read(text, tmp_path) if spec.kind == "doc")
        assert spec.edits is (mode is doc_table.Watch.ALL_EDITS)


def test_the_default_identity_is_the_brief_name_in_either_order(tmp_path):
    pr = "https://github.com/o/r/pull/12"
    table = (
        f"## Now\n\n### PRs\n\n| Work | PR | Review |\n|---|---|---|\n| Work | [r#12]({pr}) | |\n"
    )
    for brief_id in ("SkullHen.center", "center.SkullHen"):
        text = f"# Task\n\nBrief-ID: {brief_id}\n\n{table}"
        [spec] = [s for s in subscriptions.report(text, tmp_path).specs if s.kind == "pr"]
        assert spec.me == "SkullHen (Author)"


def _with_pr_row(text, pr, review=""):
    return text.replace(
        "## Watching",
        f"## Now\n\n### PRs\n\n| Work | PR | Review |\n|---|---|---|\n| Work | [r#12]({pr}) | {review} |\n\n## Watching",
    )


def test_a_pr_row_is_the_authors_unless_a_child_authors_it(tmp_path):
    pr = "https://github.com/o/r/pull/12"
    text = _with_pr_row(shared.BRIEF, pr)

    [mine] = [s for s in subscriptions.read(text, tmp_path) if s.kind == "pr"]
    [childs] = [
        s
        for s in subscriptions.report(text, tmp_path, children_prs={("o/r", "12")}).specs
        if s.kind == "pr"
    ]

    assert (mine.role, mine.ci) == ("author", False)
    assert childs.role == "parent"


def test_a_pr_row_whose_review_doc_is_the_briefs_output_is_the_reviewers(tmp_path):
    doc = tmp_path / "docket.md"
    text = _with_pr_row(shared.BRIEF, "https://github.com/o/r/pull/12", f"[doc]({doc})")
    text = text.replace("\n\n", f"\n\nOutput-Doc: {doc}\n\n", 1)

    [spec] = [s for s in subscriptions.read(text, tmp_path) if s.kind == "pr"]

    assert spec.role == "reviewer"


def test_a_review_doc_listed_for_relay_comments_still_wakes_for_body_edits(tmp_path):
    doc = tmp_path / "docket.md"
    text = _with_pr_row(shared.BRIEF, "https://github.com/o/r/pull/12", f"[doc]({doc})")
    text = doc_table.add(text, doc, "PR review conversation", doc_table.Watch.RELAY_COMMENTS)

    [spec] = [s for s in subscriptions.read(text, tmp_path) if s.kind == "doc"]

    assert spec.edits


def test_an_explicit_role_wins(tmp_path):
    pr = "https://github.com/o/r/pull/12"
    text = shared.BRIEF + f'- `lemonaid watch pr --wait {pr} --me "Reviewer (X)" --role parent`\n'

    [spec] = [s for s in subscriptions.read(text, tmp_path) if s.kind == "pr"]

    assert spec.role == "parent"


def test_command_and_file_deadline_lines_are_subscriptions(tmp_path):
    text = shared.BRIEF + (
        "- `lemonaid watch command --wait 4321`\n"
        "- `lemonaid watch file --wait done.txt --deadline 45m`\n"
    )
    by_kind = {s.kind: s for s in subscriptions.read(text, tmp_path)}
    assert by_kind["command"].target == ("4321",)
    assert by_kind["file"].deadline == "45m"


def test_a_pr_linked_anywhere_is_asked_about_unless_under_no_nudge(tmp_path):
    row, prose, fenced, quiet = (f"https://github.com/o/r/pull/{n}" for n in (12, 13, 14, 15))
    text = _with_pr_row(shared.BRIEF, row).replace(
        "## Watching",
        f"## Done\n\n- Fixed it in [r#13]({prose}), then [r#15]({quiet})\n\n"
        f"```\n{fenced}\n```\n\n## No nudge\n\n- {quiet}\n\n## Watching",
    )

    prs = {s.target[1]: s for s in subscriptions.read(text, tmp_path) if s.kind == "pr"}

    assert sorted(prs) == ["12", "13"]
    assert (prs["12"].role, prs["12"].comments, prs["12"].mentioned) == ("author", True, True)
    assert (prs["13"].role, prs["13"].comments, prs["13"].mentioned) == ("mention", False, True)


def test_with_link_nudge_off_only_pr_rows_are_watched(tmp_path):
    row, prose = (f"https://github.com/o/r/pull/{n}" for n in (12, 13))
    text = _with_pr_row(shared.BRIEF, row).replace(
        "## Watching", f"## Done\n\n- Fixed it in [r#13]({prose})\n\n## Watching"
    )

    specs = subscriptions.report(text, tmp_path, link_nudge=False).specs

    [pr] = [s for s in specs if s.kind == "pr"]
    assert (pr.target[1], pr.role, pr.mentioned) == ("12", "author", False)
