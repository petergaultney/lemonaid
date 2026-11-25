from lemonaid.comments import parse, threads


def _comment(
    comment_id: str, at: str, *, re: str | None = None, author: str = "a", day: str = "2026-11-19"
) -> str:
    re_field = f', "re": "{re}"' if re else ""
    return (
        f'# {{"id": "{comment_id}"{re_field}, "author": "{author}", '
        f'"at": "{day}T19:{at}Z", "body": "{comment_id} body"}}\n'
    )


def test_roots_follow_their_anchors_and_orphans_come_last() -> None:
    text = (
        "# [lma:Second]\nx = 1\n# [lma:First]\ny = 2\n\n# [lma:threads]\n"
        + _comment("Orphan", "01:00")
        + _comment("First", "03:00")
        + _comment("Second", "02:00")
    )

    result = threads.threads(parse.parse(text, "python"))

    assert [(t.root.comment.id, t.anchor is None) for t in result] == [
        ("Second", False),
        ("First", False),
        ("Orphan", True),
    ]


def test_replies_form_a_tree_in_the_order_they_were_written() -> None:
    text = (
        "# [lma:Root]\nx = 1\n\n# [lma:threads]\n"
        + _comment("Root", "01:00")
        + _comment("Later", "05:00", re="Root")
        + _comment("Earlier", "02:00", re="Root")
        + _comment("Deep", "03:00", re="Earlier")
    )

    result = threads.threads(parse.parse(text, "python"))

    root = result[0].root
    assert [r.comment.id for r in root.replies] == ["Earlier", "Later"]
    assert [r.comment.id for r in root.replies[0].replies] == ["Deep"]


def test_replies_are_ordered_by_time_not_by_how_the_time_is_written() -> None:
    text = (
        "# [lma:Root]\nx = 1\n\n# [lma:threads]\n"
        + _comment("Root", "01:00")
        + _comment("Fraction", "40:00.900", re="Root")
        + _comment("Whole", "40:00", re="Root")
    )

    result = threads.threads(parse.parse(text, "python"))

    assert [r.comment.id for r in result[0].root.replies] == ["Whole", "Fraction"]


def test_resolving_a_comment_resolves_every_reply_below_it() -> None:
    text = (
        "# [lma:Root]\nx = 1\n\n# [lma:threads]\n"
        + _comment("Root", "01:00")
        + _comment("Closed", "02:00", re="Root")
        + _comment("Below", "03:00", re="Closed")
        + _comment("Open", "04:00", re="Root")
        + '# {"resolves": "Closed", "author": "a", "at": "2026-11-19T19:05:00Z"}\n'
    )

    result = threads.threads(parse.parse(text, "python"))

    closed, still_open = result[0].root.replies
    assert (result[0].root.resolved, closed.resolved, closed.replies[0].resolved) == (
        False,
        True,
        True,
    )
    assert still_open.resolved is False


def test_a_reused_id_and_a_cycle_are_left_out_of_the_tree() -> None:
    text = (
        "# [lma:Root]\nx = 1\n\n# [lma:threads]\n"
        + _comment("Root", "01:00")
        + _comment("Root", "02:00", re="Root")
        + _comment("A1", "03:00", re="B2")
        + _comment("B2", "04:00", re="A1")
    )

    result = threads.threads(parse.parse(text, "python"))

    assert [(t.root.comment.at, t.root.replies) for t in result] == [("2026-11-19T19:01:00Z", ())]


def _reply_to(comment_id: str) -> str:
    return f', "re": "{comment_id}"'


def test_a_very_long_chain_of_replies_is_read_without_recursion() -> None:
    records = [
        f'# {{"id": "C{i}"{_reply_to(f"C{i - 1}") if i else ""}, "author": "a", '
        f'"at": "2026-11-19T19:00:00Z", "body": "b"}}\n'
        for i in range(2000)
    ]
    doc = parse.parse("# [lma:C0]\nx = 1\n\n# [lma:threads]\n" + "".join(records), "python")

    result = threads.threads(doc)

    depth, node = 0, result[0].root
    while node.replies:
        depth, node = depth + 1, node.replies[0]
    assert (doc.errors, depth, [c.id for c in threads.unanswered(doc, set())]) == (
        (),
        1999,
        ["C1999"],
    )
