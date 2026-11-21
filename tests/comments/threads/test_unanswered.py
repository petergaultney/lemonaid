from lemonaid.comments import parse, threads


def _text(*records: str) -> str:
    return "# [lma:Root]\nx = 1\n\n# [lma:threads]\n" + "".join(f"# {r}\n" for r in records)


def _comment(
    comment_id: str, author: str, *, re: str | None = None, minute: int = 0, lemon: bool = False
) -> str:
    re_field = f', "re": "{re}"' if re else ""
    by_field = ', "by": "lemon"' if lemon else ""
    return (
        f'{{"id": "{comment_id}"{re_field}, "author": "{author}", '
        f'"at": "2026-11-19T19:{minute:02}:00Z", "body": "b"{by_field}}}'
    )


def _resolution(comment_id: str) -> str:
    return (
        f'{{"resolves": "{comment_id}", "author": "caleb.gregory", "at": "2026-11-19T20:00:00Z"}}'
    )


def test_a_question_nobody_answered_is_unanswered() -> None:
    doc = parse.parse(_text(_comment("Root", "caleb.gregory")), "python")

    result = threads.unanswered(doc, {"Claude"})

    assert [c.id for c in result] == ["Root"]


def test_my_reply_answers_it() -> None:
    doc = parse.parse(
        _text(_comment("Root", "caleb.gregory"), _comment("Mine", "Claude", re="Root")), "python"
    )

    result = threads.unanswered(doc, {"Claude"})

    assert result == []


def test_each_branch_is_answered_on_its_own() -> None:
    doc = parse.parse(
        _text(
            _comment("Root", "caleb.gregory"),
            _comment("Mine", "Claude", re="Root", minute=1),
            _comment("Followup", "caleb.gregory", re="Root", minute=2),
            _comment("OnMine", "caleb.gregory", re="Mine", minute=3),
        ),
        "python",
    )

    result = threads.unanswered(doc, {"Claude"})

    assert [c.id for c in result] == ["OnMine", "Followup"]


def test_a_resolved_branch_needs_no_answer() -> None:
    doc = parse.parse(
        _text(
            _comment("Root", "caleb.gregory"),
            _comment("Mine", "Claude", re="Root", minute=1),
            _comment("Aside", "caleb.gregory", re="Root", minute=2),
            _resolution("Aside"),
        ),
        "python",
    )

    result = threads.unanswered(doc, {"Claude"})

    assert result == []


def test_resolving_the_only_reply_leaves_the_question_answered() -> None:
    doc = parse.parse(
        _text(
            _comment("Root", "caleb.gregory"),
            _comment("Mine", "Claude", re="Root", minute=1),
            _resolution("Mine"),
        ),
        "python",
    )

    result = threads.unanswered(doc, {"Claude"})

    assert result == []


def test_another_lemon_s_answer_to_a_person_does_not_wait_on_me() -> None:
    doc = parse.parse(
        _text(
            _comment("Root", "caleb.gregory"),
            _comment("Theirs", "RoastJet (Reviewer)", re="Root", minute=1, lemon=True),
        ),
        "python",
    )

    result = threads.unanswered(doc, {"HillyHad (Author)"})

    assert result == []


def test_a_lemon_s_reply_to_my_comment_waits_on_me() -> None:
    doc = parse.parse(
        _text(
            _comment("Root", "caleb.gregory"),
            _comment("Mine", "HillyHad (Author)", re="Root", minute=1, lemon=True),
            _comment("Theirs", "RoastJet (Reviewer)", re="Mine", minute=2, lemon=True),
        ),
        "python",
    )

    result = threads.unanswered(doc, {"HillyHad (Author)"})

    assert [c.id for c in result] == ["Theirs"]


def test_a_thread_a_lemon_starts_waits_on_every_other_lemon() -> None:
    doc = parse.parse(_text(_comment("Root", "RoastJet (Reviewer)", lemon=True)), "python")

    result = threads.unanswered(doc, {"HillyHad (Author)"})

    assert [c.id for c in result] == ["Root"]


def test_a_person_s_reply_waits_on_every_lemon() -> None:
    doc = parse.parse(
        _text(
            _comment("Root", "caleb.gregory"),
            _comment("Theirs", "RoastJet (Reviewer)", re="Root", minute=1, lemon=True),
            _comment("Followup", "caleb.gregory", re="Theirs", minute=2),
        ),
        "python",
    )

    result = threads.unanswered(doc, {"HillyHad (Author)"})

    assert [c.id for c in result] == ["Followup"]
