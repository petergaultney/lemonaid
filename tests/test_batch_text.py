from lemonaid.watch import batch_text, clip, delivery

_closing = batch_text._closing


def test_a_single_event_without_comments_only_says_lemonaid_keeps_watching():
    assert _closing("plain mail", "pushes the next batch") == "lemonaid keeps watching."


def test_several_events_name_the_batch():
    message = delivery.Labeled("a; b", "two", events=2)

    assert _closing(message, "pushes the next batch") == (
        "Handle all of it. lemonaid keeps watching and pushes the next batch."
    )


def test_the_comment_sentence_appears_only_with_a_comment_and_names_a_cut_only_when_cut():
    whole = delivery.Labeled("c", "comment", comments=True)
    cut = delivery.Labeled(clip.shorten("x" * 50, 10), "comment", comments=True)

    assert _closing(whole, "n") == "Comments are included in full. lemonaid keeps watching."
    assert "fetch one only if a cut marks it as omitted" in _closing(cut, "n")


def test_a_rearming_waiter_gets_no_watching_sentence():
    assert _closing("mail") == ""


def test_a_batch_reads_label_content_rule_closing():
    message = delivery.Labeled("body", "PR #1 CI passed")

    assert batch_text.compose(message, "pushes the next batch") == (
        "PR #1 CI passed\n\nbody\n\n---\nlemonaid keeps watching."
    )


def test_an_unlabeled_message_gets_the_default_lead_and_a_rearm_sentence_follows_the_closing():
    assert batch_text.compose("mail", then="Then rearm it.") == (
        "lemonaid watch event:\n\nmail\n\n---\nThen rearm it."
    )
