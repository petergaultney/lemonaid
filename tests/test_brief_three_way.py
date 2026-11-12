import pytest

from lemonaid.brief import three_way

_BASE = "title\n\none\ntwo\nthree\n\nend\n"


@pytest.mark.parametrize(
    ("ours", "theirs", "expected"),
    [
        ("title\n\none\nTWO\nthree\n\nend\n", _BASE, "title\n\none\nTWO\nthree\n\nend\n"),
        (
            _BASE,
            "title\n\none\ntwo\nthree\n\nend\nmore\n",
            "title\n\none\ntwo\nthree\n\nend\nmore\n",
        ),
        (
            "TITLE\n\none\ntwo\nthree\n\nend\n",
            "title\n\none\ntwo\nthree\n\nEND\n",
            "TITLE\n\none\ntwo\nthree\n\nEND\n",
        ),
        (
            "title\n\none\nTWO\nthree\n\nend\n",
            "title\n\none\nTWO\nthree\n\nend\n",
            "title\n\none\nTWO\nthree\n\nend\n",
        ),
        (
            "title\n\none\nthree\n\nend\n",
            "title\n\none\ntwo\nthree\n\nend\nmore\n",
            "title\n\none\nthree\n\nend\nmore\n",
        ),
    ],
    ids=["only ours", "only theirs", "different lines", "same change", "delete and append"],
)
def test_merge_takes_each_sides_change(ours, theirs, expected):
    result = three_way.merge(_BASE, ours, theirs, "mine", "theirs")

    assert result == three_way.Merged(expected, 0)


def test_merge_marks_lines_both_sides_changed_differently():
    ours = "title\n\none\nmine\nthree\n\nend\n"
    theirs = "title\n\none\nyours\nthree\n\nend\n"

    result = three_way.merge(_BASE, ours, theirs, "mine", "theirs")

    assert result == three_way.Merged(
        "title\n\none\n<<<<<<< mine\nmine\n=======\nyours\n>>>>>>> theirs\nthree\n\nend\n", 1
    )


def test_merge_puts_a_marker_on_its_own_line_after_a_last_line_without_a_newline():
    result = three_way.merge("a\nb", "a\nmine", "a\nyours", "mine", "theirs")

    assert result.text == "a\n<<<<<<< mine\nmine\n=======\nyours\n>>>>>>> theirs\n"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a\n<<<<<<< mine\nb\n=======\nc\n>>>>>>> theirs\n", 2),
        ("```\n<<<<<<< example\nleft\n>>>>>>> example\n```\n", 0),
        ("Heading\n=======\n", 0),
    ],
    ids=["its own markers", "other labels", "a setext heading"],
)
def test_marker_count_counts_only_markers_with_the_merges_labels(text, expected):
    assert three_way.marker_count(text, "mine", "theirs") == expected
