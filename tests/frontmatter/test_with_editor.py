from lemonaid.brief import frontmatter, frontmatter_edit


def test_an_editor_joins_contributors_once():
    text = "---\ntype: Brief\ncontributors:\n  - BlessBar\nbrief-id: t.SkullHen\n---\n# T\n"

    once = frontmatter_edit.with_editor(text, "PriceHum")

    assert frontmatter.fields(once)["contributors"] == ["BlessBar", "PriceHum"]
    assert frontmatter_edit.with_editor(once, "PriceHum") == once
    assert frontmatter_edit.with_editor(text, "BlessBar") == text


def test_an_older_edited_by_key_is_renamed_in_place():
    text = "---\ntype: Brief\nedited-by: # who\n  - BlessBar\nbrief-id: t.SkullHen\n---\n# T\n"

    assert frontmatter_edit.with_editor(text, "PriceHum") == (
        "---\ntype: Brief\ncontributors:\n  - BlessBar\n  - PriceHum\n"
        "brief-id: t.SkullHen\n---\n# T\n"
    )
    assert frontmatter_edit.with_editor(text, "BlessBar") == text.replace(
        "edited-by:", "contributors:"
    )


def test_a_brief_without_a_block_or_editor_is_unchanged():
    assert frontmatter_edit.with_editor("# T\n", "PriceHum") == "# T\n"
    assert (
        frontmatter_edit.with_editor("---\ntype: Brief\n---\n# T\n", "")
        == "---\ntype: Brief\n---\n# T\n"
    )
