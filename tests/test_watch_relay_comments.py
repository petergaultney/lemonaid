from lemonaid.watch import relay_comments

_ASKED = '{==the claim==}{{authorId="1" author="Peter Gaultney">>is this true?<<}}'
_ANSWERED = _ASKED + '{{authorId="s" author="Author (MotorHoe)">>Yes.<<}}'


def test_a_thread_is_unanswered_until_its_last_block_is_mine():
    text = f"Intro.\n\n{_ASKED}\n\nMiddle.\n\n{_ANSWERED}\n"

    assert relay_comments.unanswered_threads(text, {"Author (MotorHoe)"}) == [_ASKED]


def test_a_legacy_name_counts_as_mine():
    thread = _ASKED + '{{author="Claude">>Checked.<<}}'

    assert relay_comments.unanswered_threads(thread, {"Author (MotorHoe)", "Claude"}) == []


def test_author_falls_back_to_author_id_and_attributes_may_come_in_any_order():
    assert relay_comments.unanswered_threads('{{authorId="Claude">>note<<}}', {"Claude"}) == []
    assert (
        relay_comments.unanswered_threads(
            '{{author="Claude" authorId="sess" extra="x">>note<<}}', {"Claude"}
        )
        == []
    )


def test_a_gap_between_blocks_splits_the_thread():
    text = '{{author="Peter">>one<<}} {{author="Claude">>two<<}}'

    assert relay_comments.unanswered_threads(text, {"Claude"}) == ['{{author="Peter">>one<<}}']


def test_the_body_keeps_highlighted_text_and_drops_blocks():
    assert relay_comments.body_without_threads(f"A {_ANSWERED} B") == "A the claim B"


def test_the_gist_names_the_last_author_and_flattens_newlines():
    assert relay_comments.thread_gist('{{author="Peter">>line one\nline two<<}}') == (
        "Peter: line one line two"
    )
