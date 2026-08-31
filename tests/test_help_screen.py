"""The key reference: what it lists, and that it cannot go stale."""

import dataclasses

from lemonaid.config import KeybindingsConfig
from lemonaid.inbox.tui.help_screen import _SECTIONS, _halves, help_lines


def _entries(kb: KeybindingsConfig) -> dict[str, str]:
    return {desc: keys for _title, rows in help_lines(kb) for keys, desc in rows}


def test_every_listed_field_exists_on_the_config():
    """A renamed keybinding field fails here rather than vanishing from the list."""
    fields = {f.name for f in dataclasses.fields(KeybindingsConfig)}

    assert {field for _t, rows in _SECTIONS for field, _d in rows} <= fields


def test_the_keys_shown_are_the_ones_configured():
    kb = KeybindingsConfig(archive="X")

    assert "X" in _entries(kb)["Archive - remove it from the list"]


def test_an_unbound_key_is_left_out():
    assert any("Quit" in desc for desc in _entries(KeybindingsConfig()))
    assert not any("Quit" in desc for desc in _entries(KeybindingsConfig(quit="")))


def test_alternatives_are_shown_together():
    assert _entries(KeybindingsConfig(archive="aD"))["Archive - remove it from the list"] == "a / D"


def test_a_modifier_key_is_spelled_out():
    kb = KeybindingsConfig(move_pin_up="shift+up")

    assert _entries(kb)["Move a pinned session up one slot"] == "Shift+up"


def test_the_pin_keys_are_listed():
    listed = _entries(KeybindingsConfig())

    assert "Pin the selected session, or unpin it" in listed
    assert "Move a pinned session down one slot" in listed


def test_the_columns_are_close_to_the_same_height():
    """Splitting by section count left one column twice the other's height."""
    sections = [(t, r) for t, r in help_lines(KeybindingsConfig()) if r]
    left, right = _halves(sections)

    def lines(half):
        return sum(2 + len(rows) for _title, rows in half)

    assert abs(lines(left) - lines(right)) <= 3


def test_a_split_keeps_every_section_and_their_order():
    sections = [(t, r) for t, r in help_lines(KeybindingsConfig()) if r]
    left, right = _halves(sections)

    assert left + right == sections


def test_both_columns_get_something():
    left, right = _halves([(t, r) for t, r in help_lines(KeybindingsConfig()) if r])

    assert left and right
