"""Reading the labelled parts of `## Now`, in either form a worker writes them."""

from lemonaid.brief import now


def test_labelled_bullets_split_into_parts():
    parsed = now.parse(
        "- Done: the parser.\n"
        "- Next: the popup.\n"
        "- Needs Peter: nothing.\n"
        "- Waiting on:\n"
        "  - PR #74 review\n"
        "  - CI\n"
        "- a stray note\n"
    )

    assert parsed == now.Now(
        needs="",
        waiting_on="- PR #74 review\n- CI",
        next="the popup.",
        done="the parser.",
        other="- a stray note",
    )


def test_sub_headings_split_into_parts_and_unknown_ones_are_kept():
    parsed = now.parse(
        "### Done\n- a\n- b\n\n"
        "### Needs Peter\nPick one:\n- A\n- B\n\n"
        "### Waiting on\nnothing\n\n"
        "### Misc\nfree text\n"
    )

    assert parsed.done == "- a\n- b"
    assert parsed.needs == "Pick one:\n- A\n- B"
    assert parsed.waiting_on == ""
    assert parsed.other == "### Misc\nfree text"


def test_labels_ignore_case_emphasis_and_a_trailing_colon():
    parsed = now.parse("### needs peter:\nanswer\n\n- **Waiting On**: CI\n")

    assert (parsed.needs, parsed.waiting_on) == ("answer", "CI")


def test_a_lead_line_keeps_its_sub_bullets():
    parsed = now.parse("- Needs Peter: pick a colour\n  - yellow\n  - bold\n- Next: tests\n")

    assert parsed.needs == "pick a colour\n- yellow\n- bold"
    assert parsed.next == "tests"


def test_summary_is_one_line():
    assert now.summary("") == ""
    assert now.summary("review") == "review"
    assert now.summary("Pick one:\n- A\n- B") == "Pick one:"
    assert now.summary("- PR #74 review\n  - details\n- CI") == "PR #74 review (+1 more)"


def test_needs_names_whoever_the_worker_wrote():
    assert now.parse("- Needs: a key\n") == now.Now(needs="a key")
    assert now.parse("### Needs you\nan answer\n") == now.Now(
        needs="an answer", needs_label="Needs you"
    )
