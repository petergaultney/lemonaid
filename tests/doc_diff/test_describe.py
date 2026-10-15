import pytest

from lemonaid.watch import doc_diff


def test_several_hunks_use_new_line_ranges_and_nearest_headings():
    old = "# Review\nold\nunchanged\n## Thread: scores\nold score\nend\n"
    new = "# Review\nfirst\nsecond\nunchanged\n## Thread: scores\nnew score\nend\n"

    summary, hunks = doc_diff.describe(old, new)

    assert summary == "+3/-2 lines"
    assert hunks == (
        "lines 2-3 [# Review]; 1 removed line(s)\n+ first\n+ second\n"
        "line 6 [## Thread: scores]; 1 removed line(s)\n+ new score"
    )


def test_a_hunk_before_any_heading():
    assert doc_diff.describe("intro\n# Title\n", "new intro\n# Title\n") == (
        "+1/-1 lines",
        "line 1 [before any heading]; 1 removed line(s)\n+ new intro",
    )


@pytest.mark.parametrize(
    ("old", "new", "location"),
    [
        ("gone\n# Next\n", "# Next\n", "after line 0 [before any heading]"),
        ("# Title\ngone\n## Next\n", "# Title\n## Next\n", "after line 1 [# Title]"),
        ("# Title\ngone\n", "# Title\n", "after line 1 [# Title]"),
        ("gone\n", "", "after line 0 [before any heading]"),
    ],
)
def test_deletion_only_hunks(old, new, location):
    assert doc_diff.describe(old, new) == (
        "+0/-1 lines",
        f"{location}; 1 removed line(s)",
    )


def test_hunk_cap_keeps_totals_and_counts_omitted_hunks():
    old = "\n".join(f"old {i}\nkeep {i}" for i in range(8))
    new = old.replace("old", "new")

    summary, hunks = doc_diff.describe(old, new)

    assert summary == "+8/-8 lines"
    assert hunks.count("removed line(s)") == 5
    assert "+ new 4" in hunks
    assert "+ new 5" not in hunks
    assert hunks.endswith("3 more hunk(s) omitted")


def test_character_caps_bound_excerpt_and_heading():
    summary, hunks = doc_diff.describe("", "# " + "h" * 1000 + "\n" + "x" * 10000)

    assert summary == "+2/-0 lines"
    assert "882 characters omitted" in hunks  # heading
    assert "10507 characters omitted" in hunks  # rendered added text
    assert len(hunks) < 800


@pytest.mark.parametrize("level", range(1, 7))
def test_all_atx_heading_levels_and_changed_headings(level):
    heading = "#" * level + " Thread: answer"
    assert f"[{heading}]" in doc_diff.describe("old\n", heading + "\nanswer\n")[1]


def test_fenced_code_is_not_a_heading():
    old = "# Thread\n```markdown\n## example\n```\nold\n"
    new = old.replace("old", "answer")
    assert "line 5 [# Thread]" in doc_diff.describe(old, new)[1]


def test_diff_marker_text_is_counted_as_content():
    assert doc_diff.describe("--- old\n", "+++ new\n")[0] == "+1/-1 lines"
