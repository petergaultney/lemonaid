from lemonaid.rules import rule_text
from tests.rules import shared


def test_a_list_item_runs_to_the_next_item_at_its_level():
    assert rule_text.quote(shared.RULES, "- **A PR ready to merge") == (
        "- **A PR ready to merge gets the merge Status.** Nothing else, and no question.\n"
        "  The user merges from the Status."
    )


def test_a_numbered_item_keeps_its_nested_items():
    assert rule_text.quote(shared.RULES, "2. **Keep the Status") == (
        "2. **Keep the Status true.**\n   - It says what you wait on."
    )


def test_a_paragraph_runs_to_a_blank_line_or_heading():
    text = "Intro.\n\nThe rule is this,\nwrapped here.\n## Next\nMore."

    assert rule_text.quote(text, "The rule is") == "The rule is this,\nwrapped here."


def test_an_indented_item_is_dedented():
    text = "- Outer\n  - **Inner rule** text\n    more of it\n  - Sibling"

    assert rule_text.quote(text, "- **Inner rule") == "- **Inner rule** text\n  more of it"


def test_a_rule_not_there_quotes_nothing():
    assert rule_text.quote(shared.RULES, "- **Gone") == ""


def test_a_long_rule_is_cut():
    quoted = rule_text.quote("- **Long** " + "word " * 1000, "- **Long")

    assert len(quoted) <= 2000
    assert quoted.endswith("...")
