"""The `Hidden:` header line."""

from lemonaid.brief import hidden

_BRIEF = "# t\n\nStatus: working\n\n## Goal\nHidden: yes\n"


def test_only_the_header_counts():
    assert not hidden.is_hidden(_BRIEF)
    assert hidden.is_hidden("# t\n\nhidden: TRUE\n\n## Goal\n")
    assert not hidden.is_hidden("# t\n\nHidden: no\n\n## Goal\n")


def test_hiding_adds_the_line_under_the_title_and_showing_removes_it():
    out = hidden.with_hidden(_BRIEF, True)

    assert out == "# t\n\nHidden: yes\n\nStatus: working\n\n## Goal\nHidden: yes\n"
    assert hidden.with_hidden(out, False) == _BRIEF
    assert hidden.with_hidden(out, True) == out
