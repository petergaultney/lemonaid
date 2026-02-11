"""Tests for configuration parsing."""

from lemonaid.config import KeybindingsConfig, _parse_config
from lemonaid.inbox.tui.app import _build_bindings


def test_keybindings_defaults():
    """KeybindingsConfig has expected defaults."""
    kb = KeybindingsConfig()
    assert kb.quit == "q"
    assert kb.refresh == "g"
    assert kb.jump_unread == "u"
    assert kb.mark_read == "m"
    assert kb.archive == "a"
    assert kb.rename == "r"
    assert kb.history == "h"
    assert kb.copy_resume == "c"
    assert kb.up_down == ""


def test_parse_keybindings_partial_override():
    """Parsing config with partial keybindings uses defaults for unspecified."""
    data = {
        "tui": {
            "keybindings": {
                "quit": "qQ",
                "up_down": "kj",
            }
        }
    }
    config = _parse_config(data)
    kb = config.tui.keybindings

    # Overridden
    assert kb.quit == "qQ"
    assert kb.up_down == "kj"

    # Defaults preserved
    assert kb.refresh == "g"
    assert kb.jump_unread == "u"
    assert kb.mark_read == "m"
    assert kb.archive == "a"
    assert kb.rename == "r"


def test_parse_keybindings_empty_section():
    """Parsing config with empty keybindings section uses all defaults."""
    data = {"tui": {"keybindings": {}}}
    config = _parse_config(data)
    kb = config.tui.keybindings

    assert kb.quit == "q"
    assert kb.up_down == ""


def test_parse_keybindings_missing_section():
    """Parsing config without keybindings section uses all defaults."""
    data = {"tui": {}}
    config = _parse_config(data)
    kb = config.tui.keybindings

    assert kb.quit == "q"
    assert kb.up_down == ""


def test_build_bindings_single_key():
    """Single key creates one visible binding."""
    bindings = _build_bindings("q", "quit", "Quit")
    assert len(bindings) == 1
    assert bindings[0].key == "q"
    assert bindings[0].action == "quit"
    assert bindings[0].description == "Quit"
    assert bindings[0].show is True


def test_build_bindings_multiple_keys():
    """Multiple keys create one visible + hidden bindings."""
    bindings = _build_bindings("qQe", "quit", "Quit")
    assert len(bindings) == 3

    # First is visible
    assert bindings[0].key == "q"
    assert bindings[0].show is True

    # Rest are hidden
    assert bindings[1].key == "Q"
    assert bindings[1].show is False
    assert bindings[2].key == "e"
    assert bindings[2].show is False


def test_build_bindings_empty():
    """Empty keys string returns no bindings."""
    bindings = _build_bindings("", "quit", "Quit")
    assert bindings == []


def test_build_bindings_hidden():
    """show=False makes all bindings hidden."""
    bindings = _build_bindings("qQ", "refresh", "Refresh", show=False)
    assert len(bindings) == 2
    assert bindings[0].show is False
    assert bindings[1].show is False
