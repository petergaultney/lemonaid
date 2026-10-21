from lemonaid.brief import frontmatter, frontmatter_edit, identity, status

from .shared import DEFAULTS, LEGACY


def test_the_header_view_is_what_the_old_parsers_read():
    migrated = frontmatter_edit.carried(LEGACY, LEGACY, DEFAULTS)

    assert frontmatter.legacy(migrated) == (
        "# Task\n\nBrief-ID: task.SkullHen\nParent: hq.LemonAce\nGroups: lemonaid, misc\n"
        "Hidden: yes\n\n## Now\n\n- Starting.\n"
    )
    assert identity.read(migrated) == "task.SkullHen"
    assert status.split(migrated).title == "Task"


def test_a_brief_without_a_block_is_read_unchanged():
    assert frontmatter.legacy(LEGACY) == LEGACY


def test_a_yaml_comment_is_never_the_title():
    text = "---\n# not the title\nbrief-id: task.SkullHen\n---\n# Task\n\n## Now\n"

    assert status.split(text).title == "Task"


def test_a_block_that_does_not_parse_still_shows_its_plain_keys():
    text = "---\nbrief-id: task.SkullHen\nstatus: [blocked\n---\n# Task\n\n## Now\n"

    assert identity.read(text) == "task.SkullHen"
