"""Configured hide keys participate in inbox conflict diagnostics."""

from lemonaid import keys
from lemonaid.config import KeybindingsConfig


def test_hide_conflicts_with_archive():
    assert keys.conflicts(KeybindingsConfig(hide="a")) == [
        "in the inbox view, 'a' is bound to archive and hide"
    ]


def test_hide_can_be_disabled():
    assert keys.conflicts(KeybindingsConfig(hide="")) == []


def test_save_size_is_one_modified_key():
    assert keys.conflicts(KeybindingsConfig(first="ctrl+s")) == [
        "in the inbox view, 'ctrl+s' is bound to first and save_size"
    ]
