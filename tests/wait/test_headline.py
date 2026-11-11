from lemonaid.watch import batch_wait, delivery


def test_headline_names_the_first_three_events_and_counts_the_rest():
    labels = ["#519 merged", "CardsTie -> merge", "mail from HeardCue", "file changed"]

    assert batch_wait._headline(labels) == (
        "#519 merged; CardsTie -> merge; mail from HeardCue (+1 more)"
    )


def test_headline_is_cut_to_one_terminal_line():
    assert len(batch_wait._headline(["x" * 300])) == 110


def test_mail_is_named_for_its_sender_and_other_sources_fall_back_to_their_kind():
    assert batch_wait._from("From: TreatShy.review-x (codex:01a)\nSent: now\n\nhi") == "TreatShy"
    assert batch_wait._fallback("pr: https://x/1") == "pr event"


def test_a_plain_message_has_no_label():
    assert delivery.label_of("plain") == ""
    assert delivery.label_of(delivery.Labeled("body", "doc comments")) == "doc comments"
