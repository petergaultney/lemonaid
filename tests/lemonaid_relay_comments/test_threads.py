from lemonaid_relay_comments import threads

_ASKED = '{==the claim==}{{authorId="1" author="Sam Rivera">>is this true?<<}}'
_ANSWERED = _ASKED + '{{authorId="s" author="MotorHoe (Author)">>Yes.<<}}'


def test_a_thread_is_unanswered_until_its_last_block_is_mine():
    text = f"Intro.\n\n{_ASKED}\n\nMiddle.\n\n{_ANSWERED}\n"

    assert threads.unanswered(text, {"MotorHoe (Author)"}) == [_ASKED]


def test_a_legacy_name_counts_as_mine():
    thread = _ASKED + '{{author="Claude">>Checked.<<}}'

    assert threads.unanswered(thread, {"MotorHoe (Author)", "Claude"}) == []


def test_author_falls_back_to_author_id_and_attributes_may_come_in_any_order():
    assert threads.unanswered('{{authorId="Claude">>note<<}}', {"Claude"}) == []
    assert (
        threads.unanswered('{{author="Claude" authorId="sess" extra="x">>note<<}}', {"Claude"})
        == []
    )


def test_a_gap_between_blocks_splits_the_thread():
    text = '{{author="Sam">>one<<}} {{author="Claude">>two<<}}'

    assert threads.unanswered(text, {"Claude"}) == ['{{author="Sam">>one<<}}']


def test_the_body_keeps_highlighted_text_and_drops_blocks():
    assert threads.body_without_threads(f"A {_ANSWERED} B") == "A the claim B"


def test_the_gist_names_the_last_author_and_flattens_newlines():
    assert threads.gist('{{author="Sam">>line one\nline two<<}}') == ("Sam: line one line two")


def test_thread_text_keeps_line_breaks_and_the_whole_comment():
    body = "line one\nline two " + "x" * 3000

    assert threads.full_text(f'{{{{author="Sam">>{body}<<}}}}') == f"Sam:\n{body}"


def test_thread_text_is_cut_with_a_pointer_to_the_source():
    text = threads.full_text('{{author="Sam">>' + "x" * 5000 + "<<}}")

    assert "1000 characters omitted; read the source" in text


def test_a_thread_key_is_unchanged_from_before_relay_was_a_plugin():
    """sha1 of the layout-normalized thread, so a waiter's saved cursors still match."""
    assert threads.key(_ASKED) == "fe6a945ce8d38e28"
    assert threads.key(_ASKED.replace(" ", "  ")) == threads.key(_ASKED)
