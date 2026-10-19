import pytest

from lemonaid.brief import check, doc_table, migrate, now, now_edit, section_edit, sections, status
from lemonaid.watch import subscriptions, wait_requirements

LEGACY = """# task

Brief-ID: task.IndexElf
Parent: lead.IndexElf

## Now

Current prose.

### Waiting on

- review

### Next

- write docs

### PRs

| Work | PR | Review |
|---|---|---|
| Fix | [r#12](https://github.com/o/r/pull/12) | |

### Done

- implemented

## Questions

## Goal

Keep this exactly.

## Watching
"""


def test_migration_preserves_readers_and_subscriptions(tmp_path):
    old = LEGACY.replace(
        "### Done",
        "### Docs\n\n"
        + "\n".join(doc_table.render([doc_table.Row(tmp_path / "review.md", "Review")]))
        + "\n\n### Done",
    )
    migrated = migrate.layout(old)
    assert migrate.layout(migrated) == migrated
    for name in ("Next", "PRs", "Docs", "Done"):
        assert sections.find(migrated, name).level == 2
    assert "### Waiting on\n\n- review" in migrated
    assert "## Goal\n\nKeep this exactly." in migrated
    assert doc_table.rows(migrated) == doc_table.rows(old)
    assert subscriptions.read(migrated, tmp_path) == subscriptions.read(old, tmp_path)
    assert wait_requirements.needs_unified(migrated, False)
    assert now.parse(status.split(migrated).now) == now.parse(status.split(old).now)
    assert check.structure(migrated) == []
    assert any("brief migrate" in w for w in check.warnings(old))
    assert check.warnings(migrated) == []


def test_migration_only_promotes_exact_names_outside_fences():
    text = LEGACY.replace("### Next", "```markdown\n### Docs\n- example\n```\n\n### Next").replace(
        "### Done", "### Next steps\n\n- custom\n\n### Done"
    )
    migrated = migrate.layout(text)
    assert "```markdown\n### Docs\n- example\n```" in migrated
    assert sections.find(migrated, "Next steps").level == 3
    assert sections.find(migrated, "Docs") is None


def test_migration_refuses_collisions_without_choosing_a_body():
    with pytest.raises(ValueError, match=r"Ambiguous.*Next"):
        migrate.layout(LEGACY.replace("## Goal", "## Next\n\n- other\n\n## Goal"))


@pytest.mark.parametrize("replace_all", [False, True])
def test_now_refuses_reintroducing_promoted_headings(replace_all):
    text = migrate.layout(LEGACY)
    with pytest.raises(ValueError, match="brief section set"):
        now_edit.replace_progress(text, "### Next\n\n- new", replace_all)
    out = now_edit.replace_progress(text, "### Waiting on\n\n- CI")
    assert sections.body(out, sections.find(out, "Next")) == ("- write docs",)


def test_generic_sections_preserve_siblings_and_support_nested_headings():
    text = section_edit.change(LEGACY, "Notes", lambda _: ["one", "", "### Detail", "", "two"])
    assert sections.body(text, sections.find(text, "Detail")) == ("two",)
    text = section_edit.change(text, "Detail", lambda _: ["changed"])
    assert "one\n\n### Detail\n\nchanged" in text
    assert "Keep this exactly." in text
    text = section_edit.change(text, "Notes", lambda _: ())
    assert sections.find(text, "Detail") is None
    assert text.endswith("## Watching\n")


def test_generic_bullets_work_at_both_levels_and_keep_nested_sections():
    text = section_edit.add(migrate.layout(LEGACY), "Goal", "write code")
    text = section_edit.add(text, "Waiting on", "CI")
    text = section_edit.with_item(text, "write code", section_edit.item("finish code"), "Goal")
    assert "- finish code" in text and "- CI" in text
    text = section_edit.with_item(text, "finish code", (), "Goal")
    assert "Keep this exactly." in text
    text = section_edit.add(text, "Now", "fresh prose bullet")
    assert "### Waiting on" in text
    assert "- fresh prose bullet" in sections.body(text, sections.find(text, "Now"), direct=True)


def test_generic_heading_ambiguity_names_candidates():
    text = "# task\n\n## Notes\n\n- first\n\n## Goal\n\n### Notes\n\n- second\n"
    for change in (
        lambda: section_edit.add(text, "Notes", "x"),
        lambda: section_edit.change(text, "Notes", lambda _: ["x"]),
    ):
        with pytest.raises(ValueError, match=r"## Notes .*line 3.*### Notes .*line 9"):
            change()
    with pytest.raises(ValueError, match="2 bullets"):
        section_edit.with_item(text.replace("second", "first again"), "first", ())


def test_fenced_headings_and_bullets_are_not_edit_targets():
    text = (
        "# task\n\n## Notes\n\n````markdown\n## Goal\n```\n- example\n````\n\n## Goal\n\n- real\n"
    )
    assert sections.find(text, "Goal").level == 2
    out = section_edit.change(text, "Goal", lambda _: ["new"])
    assert "## Goal\n```\n- example" in out


def test_fenced_bullets_are_not_matched():
    text = "# task\n\n## Notes\n\n```\n- example\n```\n\n- real\n"
    with pytest.raises(ValueError, match="No bullet"):
        section_edit.with_item(text, "example", ())
    assert "- example" in section_edit.with_item(text, "real", ())


@pytest.mark.parametrize(
    "fields",
    [
        "Area: briefs",
        "Parent: lead.IndexElf\nOutput-Doc: /tmp/review.md\nArea: briefs\nGroups: docs",
    ],
)
@pytest.mark.parametrize("operation", ["replace", "remove", "section"])
def test_legacy_now_metadata_survives_edits(fields, operation):
    text = f"# task\n\n## Now\n\n### Done\n\n- implemented\n\n{fields}\n\n## Goal\n\nUnchanged.\n"
    if operation == "section":
        out = section_edit.change(text, "Done", lambda _: ["- reviewed"])
    else:
        out = section_edit.with_item(
            text, "implemented", section_edit.item("reviewed") if operation == "replace" else ()
        )
    for line in fields.splitlines():
        assert line in out.splitlines()
    assert "implemented" not in out
    assert check.structure(out) == []


def test_legacy_table_tail_fields_are_not_table_rows_and_stay_in_now(tmp_path):
    fields = "Parent: lead.IndexElf\nOutput-Doc: /tmp/review.md\nArea: briefs\nGroups: docs"
    text = LEGACY[: LEGACY.index("### Done")] + fields + "\n\n## Goal\n\nUnchanged.\n"
    assert check.structure(text) == []
    assert not subscriptions.report(text, tmp_path).problems
    out = migrate.layout(text)
    assert check.structure(out) == []
    assert subscriptions.read(out, tmp_path) == subscriptions.read(text, tmp_path)
    assert sections.body(out, sections.find(out, "PRs"))[-1].startswith("| Fix")
    for line in fields.splitlines():
        assert line in out.splitlines()
        assert out.index(line) < out.index("## PRs")
    assert section_edit.change(text, "PRs", lambda _: ()).count("Area: briefs") == 1


def test_new_nested_heading_has_the_requested_parent():
    text = "# task\n\n## Notes\n\n### Existing\n\nKeep this.\n"
    out = section_edit.change(text, "Detail", lambda _: ["New."], level=4, parent="Notes")
    assert sections.find(out, "Detail").parent == "Notes"
    assert "#### Detail" in section_edit.change(out, "Existing", lambda _: ())


def test_check_reports_duplicate_now_even_with_promoted_sections():
    text = "# task\n\n## Now\n\n## Now\n\n## Next\n\n- next\n"
    assert "`## Now` appears 2 times" in check.structure(text)


def test_now_refusal_does_not_treat_example_headings_as_promoted_sections():
    text = migrate.layout(LEGACY)
    out = now_edit.replace_progress(
        text, "Example:\n\n```markdown\n### Next\n\n- example\n```", replace_all=True
    )
    assert "```markdown\n### Next\n\n- example\n```" in out
    assert sections.body(out, sections.find(out, "Next")) == ("- write docs",)
