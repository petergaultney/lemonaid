from lemonaid.doc_plugins import protocol


def test_records_follow_their_thread_line_and_text_lines_join():
    reading = protocol.parse(
        "thread a\nlast Sam\nwaiting\ngist Sam: hi\ntext Sam:\ntext hi\ntext \ntext there\n"
        "thread b\nlast Mo\ntext Mo: ok\n"
    )

    assert reading == protocol.Reading(
        (
            protocol.Thread("a", "Sam", True, "Sam:\nhi\n\nthere", "Sam: hi"),
            protocol.Thread("b", "Mo", False, "Mo: ok", "Mo: ok"),
        ),
        (),
        True,
    )


def test_notes_and_incomplete_describe_the_whole_reading():
    reading = protocol.parse("note answer with x\nthread a\nwaiting\nincomplete\nnote and y\n")

    assert reading.notes == ("answer with x", "and y")
    assert not reading.complete
    assert [t.key for t in reading.threads] == ["a"]


def test_unknown_fields_and_fields_before_any_thread_are_skipped():
    reading = protocol.parse("version 2\nlast nobody\nthread a\ncolour red\ntext hi\n")

    assert reading.threads == (protocol.Thread("a", "", False, "hi", "hi"),)


def test_a_missing_gist_is_the_text_on_one_line_cut_to_100_characters():
    [thread] = protocol.parse("thread a\ntext one\ntext " + "x" * 200 + "\n").threads

    assert thread.gist == ("one " + "x" * 200)[:100]
