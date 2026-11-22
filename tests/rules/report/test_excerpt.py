import re

from lemonaid.rules import report


def test_a_short_message_is_shown_whole_with_the_match_in_bold():
    text = "CI is green.\n\nWant me to merge it?"

    assert report.excerpt(text, re.search(r"want me to merge", text, re.I)) == (
        "CI is green. **Want me to merge** it?"
    )


def test_a_long_message_is_cut_around_the_match():
    text = "a" * 400 + " Ready to merge? " + "b" * 400

    shown = report.excerpt(text, re.search(r"Ready to merge\?", text))

    assert shown.startswith("...aaa")
    assert shown.endswith("bbb...")
    assert "**Ready to merge?**" in shown
    assert len(shown) < 340


def test_whitespace_around_a_match_stays_outside_the_bold():
    text = "Done.\n  Merge #12?"

    assert report.excerpt(text, re.search(r"(?m)^\s*Merge #\d+\?", text)) == (
        "Done. **Merge #12?**"
    )
