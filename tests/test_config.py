"""Tests for configuration parsing."""

from pathlib import Path

import pytest

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


def test_scratch_position_defaults_to_left_and_can_be_overridden():
    assert _parse_config({}).tmux_session.scratch_position == "left"
    top = _parse_config({"tmux-session": {"scratch_position": "top"}})
    assert top.tmux_session.scratch_position == "top"


def test_card_unread_style_defaults_to_dot_and_can_be_overridden():
    assert _parse_config({}).tui.card_unread_style == "dot"
    assert _parse_config({"tui": {"card_unread_style": "bar"}}).tui.card_unread_style == "bar"


def test_project_name_colors_default_off_and_can_be_enabled():
    assert _parse_config({}).tui.project_name_colors is False
    assert _parse_config({"tui": {"project_name_colors": True}}).tui.project_name_colors is True


def test_active_row_color_defaults_and_can_be_overridden():
    assert _parse_config({}).tui.active_row_color is None
    config = _parse_config({"tui": {"active_row_color": "#123456"}})
    assert config.tui.active_row_color == "#123456"


def test_brief_cards_are_opt_in():
    assert _parse_config({}).tui.brief_status is False
    config = _parse_config({"tui": {"brief_status": True, "brief_stale_hours": 12}})
    assert config.tui.brief_status is True
    assert config.tui.brief_stale_hours == 12


def test_parse_named_tmux_window_processes():
    config = _parse_config({"tmux-window": {"named_processes": ["mops-console"]}})

    assert config.tmux_window.named_processes == ("mops-console",)


def test_named_tmux_window_processes_default_to_empty():
    assert _parse_config({}).tmux_window.named_processes == ()


def test_harness_window_defaults_to_resume_window_at_use_time():
    config = _parse_config({"tmux-session": {"resume_window": 1}})

    assert config.tmux_session.resume_window == 1
    assert config.tmux_session.harness_window is None


def test_harness_window_can_be_configured_separately():
    config = _parse_config({"tmux-session": {"resume_window": 1, "harness_window": 2}})

    assert config.tmux_session.harness_window == 2


def test_backend_submit_key_defaults_and_override(capsys):
    config = _parse_config({"backends": {"claude": {}, "codex": {"submit_key": "C-Enter"}}})

    assert config.backends["claude"].submit_key == "Enter"
    assert config.backends["codex"].submit_key == "C-Enter"
    assert not capsys.readouterr().err


def test_invalid_backend_submit_key_keeps_enter(capsys):
    config = _parse_config({"backends": {"claude": {"submit_key": "C-m"}}})

    assert config.backends["claude"].submit_key == "Enter"
    assert "submit_key must be Enter or C-Enter" in capsys.readouterr().err


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


def test_brief_pr_state_command_is_read_from_config():
    assert _parse_config({}).brief.pr_state == ""
    assert _parse_config({"brief": {"pr_state": "tool {ref}"}}).brief.pr_state == "tool {ref}"


def test_brief_vaults_expand_their_roots_and_default_to_none():
    assert _parse_config({}).brief.vaults == ()
    assert _parse_config({"brief": {"vaults": ["~/notes", "/srv/kb"]}}).brief.vaults == (
        Path.home() / "notes",
        Path("/srv/kb"),
    )


def test_brief_vaults_that_are_not_directories_are_reported_and_skipped(capsys):
    assert _parse_config({"brief": {"vaults": [7, "", "~/c"]}}).brief.vaults == (Path.home() / "c",)
    assert capsys.readouterr().err.splitlines() == [
        "Warning: [brief] vaults: ignoring 7",
        "Warning: [brief] vaults: ignoring ''",
    ]


def test_brief_vaults_that_is_not_a_list_is_reported(capsys):
    assert _parse_config({"brief": {"vaults": {"~/a": "a"}}}).brief.vaults == ()
    assert "[brief] vaults must be a list of directories, not dict" in capsys.readouterr().err


def test_default_template_can_name_another_template():
    claude = ["emacsclient -nw .", "claude", ""]
    config = _parse_config({"tmux-session": {"templates": {"claude": claude, "default": "claude"}}})

    assert config.tmux_session.get_template("default") == claude
    assert config.tmux_session.get_template("claude") == claude


def test_default_template_list_still_works():
    default = ["emacsclient -nw .", "claude", ""]
    config = _parse_config({"tmux-session": {"templates": {"default": default}}})

    assert config.tmux_session.get_template("default") == default


@pytest.mark.parametrize(
    ("alias", "reason"), [("codex", "names no template"), ("default", "names itself")]
)
def test_default_template_naming_nothing_is_rejected(capsys, alias, reason):
    config = _parse_config(
        {"tmux-session": {"templates": {"claude": ["claude"], "default": alias}}}
    )

    assert config.tmux_session.get_template("default") is None
    assert reason in capsys.readouterr().err


def test_retired_fold_statuses_mean_the_derived_states():
    tui = {"tui": {"fold_statuses": ["waiting", "working", "done"]}}
    assert _parse_config(tui).tui.fold_statuses == ["idle", "active", "done"]
