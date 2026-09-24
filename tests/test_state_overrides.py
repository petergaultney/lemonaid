"""`LEMONAID_CONFIG` and `LEMONAID_STATE_DIR`: what `scripts/sandbox` redirects."""

from pathlib import Path

from lemonaid import config
from lemonaid.tmux import navigation as tmux_navigation
from lemonaid.wezterm import navigation as wezterm_navigation


def test_config_defaults_to_the_xdg_path(monkeypatch):
    monkeypatch.delenv("LEMONAID_CONFIG", raising=False)

    assert config.get_config_path() == Path.home() / ".config" / "lemonaid" / "config.toml"


def test_config_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("LEMONAID_CONFIG", str(tmp_path / "config.toml"))

    assert config.get_config_path() == tmp_path / "config.toml"


def test_state_dir_override_wins_for_both_terminals(monkeypatch, tmp_path):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path / "state"))

    assert tmux_navigation.get_state_path() == tmp_path / "state"
    assert wezterm_navigation.get_state_path() == tmp_path / "state"
    assert (tmp_path / "state").is_dir()
