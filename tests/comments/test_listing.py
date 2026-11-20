import textwrap

from lemonaid.comments import edits, listing, parse

_AT = "2026-11-19T19:40:00Z"
_CODE = "import os\n\n\ndef f(x):\n    return x + 1\n"


def _commented(text: str, start: int, end: int, comment_id: str = "Root") -> str:
    added = edits.add_comment(
        text,
        "python",
        start,
        end,
        author="caleb.gregory",
        body="why +1?",
        at=_AT,
        comment_id=comment_id,
    )
    return edits.apply(text, added.edits)


def _replied(text: str, re_: str, *, author: str, comment_id: str) -> str:
    added = edits.reply(
        text, "python", re_, author=author, body="so 2 becomes 3", at=_AT, comment_id=comment_id
    )
    return edits.apply(text, added.edits)


def test_a_thread_shows_its_lines_and_replies_as_a_tree() -> None:
    text = _replied(
        _commented(_CODE, 12, len(_CODE)), "Root", author="HillyHad (Author)", comment_id="Reply"
    )

    shown = listing.render(text, parse.parse(text, "python"))

    assert shown == textwrap.dedent(
        """\
        Root: lines 5-6
          5 | def f(x):
          6 |     return x + 1
        - [Root] caleb.gregory (2026-11-19T19:40:00Z)
          why +1?
            - [Reply] HillyHad (Author) (re Root, 2026-11-19T19:40:00Z)
              so 2 becomes 3"""
    )


def test_unanswered_shows_only_threads_waiting_on_the_reader_and_marks_the_comment() -> None:
    text = _replied(
        _commented(_CODE, 12, 12, "Asked"), "Asked", author="HillyHad (Author)", comment_id="Done"
    )
    text = _commented(text, 0, 0, "Waiting")
    doc = parse.parse(text, "python")

    shown = listing.render(text, doc, unanswered_for={"HillyHad (Author)"})

    assert shown.splitlines()[0] == "Waiting: line 2"
    assert "UNANSWERED" in shown
    assert "Asked" not in shown


def test_a_resolved_thread_is_shown_only_when_asked() -> None:
    text = _commented(_CODE, 12, 12)
    text = edits.apply(
        text, [edits.resolve(text, "python", "Root", author="caleb.gregory", at=_AT)]
    )
    doc = parse.parse(text, "python")

    assert listing.render(text, doc) == ""
    assert "resolved" in listing.render(text, doc, with_resolved=True)


def test_an_orphan_says_its_anchor_is_gone() -> None:
    text = _commented(_CODE, 12, 12)
    text = "".join(line for line in text.splitlines(keepends=True) if "[lma:Root]" not in line)
    text = text.replace("# [/lma:Root]\n", "")

    shown = listing.render(text, parse.parse(text, "python"))

    assert shown.splitlines()[0] == "Root: orphaned, its anchor is gone"


def test_a_long_anchor_is_cut_with_a_count_of_what_is_left() -> None:
    code = "".join(f"x{n} = {n}\n" for n in range(1, 21))
    text = _commented(code, 0, len(code))

    shown = listing.render(text, parse.parse(text, "python"))

    assert "  ... 8 more line(s)" in shown
