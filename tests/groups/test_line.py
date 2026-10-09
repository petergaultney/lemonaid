from lemonaid.groups import line

BRIEF = "# Task\n\nBrief-ID: task.Ab\n\nStatus: working\n\nParent: lead.Cd\n\n## Now\n\n- x\n"


def test_a_brief_without_a_line_reads_as_none():
    assert line.read(BRIEF) is None


def test_the_line_goes_after_the_last_header_field():
    written = line.written(BRIEF, ["Inbox", "Relay"])

    assert "Parent: lead.Cd\nGroups: Inbox, Relay\n" in written
    assert line.read(written) == ("Inbox", "Relay")


def test_rewriting_replaces_the_line_and_no_groups_removes_it():
    once = line.written(BRIEF, ["Inbox"])

    assert line.read(line.written(once, ["Relay"])) == ("Relay",)
    assert line.written(once, []) == BRIEF


def test_a_groups_line_below_the_header_or_in_a_fence_is_not_the_line():
    text = BRIEF + "\n## Notes\n\nGroups: not this\n\n```\nGroups: nor this\n```\n"

    assert line.read(text) is None
