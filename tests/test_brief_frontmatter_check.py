from lemonaid.brief import check, frontmatter_check

_GOOD = (
    "---\ntype: Brief\ncreated: { at: 2026-10-21, by: BlessBar }\n"
    "responsible-parties:\n  - Sam Smith\ncontributors:\n  - BlessBar\n"
    "brief-id: t.SkullHen\n---\n# T\n\n## Now\n"
)


def test_a_complete_block_has_no_problems():
    assert frontmatter_check.problems(_GOOD) == []
    assert check.structure(_GOOD) == []


def test_a_brief_without_a_block_is_not_checked_for_one():
    assert frontmatter_check.problems("# T\n\nBrief-ID: t.SkullHen\n\n## Now\n") == []


def test_each_missing_or_wrong_key_is_reported():
    text = "---\ntype: Notes\nedited-by:\n  - Someone\ncreated: { at: 2026-10-21, by: BlessBar }\n---\n# T\n"

    assert frontmatter_check.problems(text) == [
        "The frontmatter's `type` should be `Brief`",
        "The frontmatter has no `responsible-parties` list",
        "The frontmatter's `contributors` should start with its creator, BlessBar",
    ]


def test_bad_yaml_and_a_stray_header_line_are_reported():
    assert frontmatter_check.problems("---\ntype: [Brief\n---\n# T\n")[0].startswith(
        "The frontmatter isn't valid YAML"
    )
    assert frontmatter_check.problems(_GOOD.replace("# T\n", "# T\n\nStatus: done\n")) == [
        "A `Status:` header line sits beside the frontmatter; set it in the frontmatter"
    ]
