from lemonaid.brief import frontmatter, frontmatter_edit, store

from .shared import DEFAULTS, LEGACY


def test_a_legacy_brief_moves_its_header_lines_into_a_new_block():
    migrated = frontmatter_edit.carried(LEGACY, LEGACY, DEFAULTS)

    assert migrated == (
        "---\n"
        "type: Brief\n"
        "created: { at: 2026-10-21T10:00:00-04:00, by: BlessBar }\n"
        "responsible-parties:\n"
        "  - Sam Smith\n"
        "contributors:\n"
        "  - BlessBar\n"
        "brief-id: task.SkullHen\n"
        "parent: hq.LemonAce\n"
        "groups:\n"
        "  - lemonaid\n"
        "  - misc\n"
        "hidden: true\n"
        "---\n"
        "# Task\n"
        "\n"
        "## Now\n"
        "\n"
        "- Starting.\n"
    )


def test_an_edit_round_trips_through_the_header_view():
    migrated = frontmatter_edit.carried(LEGACY, LEGACY, DEFAULTS)

    assert frontmatter_edit.carried(frontmatter.legacy(migrated), migrated, DEFAULTS) == migrated
    blocked = frontmatter_edit.carried(
        store.with_status(frontmatter.legacy(migrated), "blocked"), migrated, DEFAULTS
    )
    assert frontmatter.fields(blocked)["status"] == "blocked"
    cleared = store.with_status(frontmatter.legacy(blocked), store.CLEAR)
    assert frontmatter_edit.carried(cleared, blocked, DEFAULTS) == migrated


def test_unknown_keys_comments_and_formatting_survive_an_edit():
    text = (
        "---\n"
        "type: Brief\n"
        "# a person's note\n"
        "tags: [x, y]\n"
        "brief-id: task.SkullHen\n"
        "---\n"
        "# Task\n"
        "\n"
        "## Now\n"
    )

    edited = frontmatter_edit.carried(
        store.with_status(frontmatter.legacy(text), "done"), text, DEFAULTS
    )

    assert edited == text.replace(
        "brief-id: task.SkullHen\n", "brief-id: task.SkullHen\nstatus: done\n"
    )


def test_a_header_line_left_beside_the_block_loses_to_the_block():
    text = "---\nbrief-id: task.SkullHen\nstatus: blocked\n---\n# Task\n\nStatus: done\n\n## Now\n"

    carried = frontmatter_edit.carried(frontmatter.legacy(text), text, DEFAULTS)

    assert frontmatter.fields(carried)["status"] == "blocked"
    assert "Status:" not in carried


def _status(text: str, state: str) -> str:
    return frontmatter_edit.carried(
        store.with_status(frontmatter.legacy(text), state), text, DEFAULTS
    )


def test_name_words_survive_an_edit_and_a_migration():
    text = "---\nbrief-id: t.SkullHen\nname-words:\n  - audit\n  - ink\n---\n# T\n\n## Now\n"
    migrated = frontmatter_edit.carried(
        "# T\n\nName words: audit ink\n\n## Now\n",
        "# T\n\nName words: audit ink\n\n## Now\n",
        DEFAULTS,
    )

    assert frontmatter.fields(_status(text, "done"))["name-words"] == ["audit", "ink"]
    assert frontmatter.fields(migrated)["name-words"] == ["audit", "ink"]


def test_a_multiline_value_is_neither_shown_as_header_lines_nor_changed():
    text = "---\nbrief-id: t.SkullHen\narea: |\n  hello\n  world\n---\n# T\n\n## Now\n"

    assert "world" not in frontmatter.legacy(text)
    assert _status(text, "done") == text.replace("t.SkullHen\n", "t.SkullHen\nstatus: done\n")


def test_a_comment_inside_a_list_goes_with_it_and_a_quoted_key_is_found():
    text = (
        "---\nbrief-id: t.SkullHen\ngroups:\n  - old\n# list comment\n  - other\n"
        "'status': blocked\n---\n# T\n\n## Now\n"
    )

    removed = frontmatter_edit.carried(
        frontmatter.legacy(text).replace("Groups: old, other\n", ""), text, DEFAULTS
    )
    done = _status(text, "done")

    assert "groups" not in frontmatter.fields(removed) and "other" not in removed
    assert frontmatter.fields(done)["status"] == "done"
    assert "blocked" not in done


def test_fields_given_in_now_move_into_the_block():
    text = "---\nbrief-id: t.SkullHen\n---\n# T\n\n## Now\n"
    legacy = "# T\n\nBrief-ID: t.SkullHen\n\n## Now\n\n- Working.\n\nParent: hq.LemonAce\nArea: apps/web\n"

    edited = frontmatter_edit.carried(legacy, text, DEFAULTS)
    migrated = frontmatter_edit.carried(legacy, legacy, DEFAULTS)

    for result in (edited, migrated):
        found = frontmatter.fields(result)
        assert (found["parent"], found["area"]) == ("hq.LemonAce", "apps/web")
        assert "Parent:" not in result and "Area:" not in result


def test_a_fenced_example_is_neither_taken_nor_emptied():
    legacy = "# T\n\nBrief-ID: t.SkullHen\n\n```\nParent: fake.Parent\n```\n\n## Now\n"

    migrated = frontmatter_edit.carried(legacy, legacy, DEFAULTS)

    assert "parent" not in frontmatter.fields(migrated)
    assert "```\nParent: fake.Parent\n```" in migrated


def test_indented_and_nested_fences_hide_their_examples_too():
    for fenced in (
        "   ```\nParent: fake.Parent\n   ```",
        "````\n```\nParent: fake.Parent\n```\n````",
    ):
        legacy = f"# T\n\nBrief-ID: t.SkullHen\n\n{fenced}\n\n## Now\n"

        migrated = frontmatter_edit.carried(legacy, legacy, DEFAULTS)

        assert "parent" not in frontmatter.fields(migrated)
        assert fenced in migrated
