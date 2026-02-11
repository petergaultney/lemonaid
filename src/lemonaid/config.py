"""Configuration management for lemonaid."""

import tomllib
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any


def get_config_path() -> Path:
    """Get the path to the lemonaid config file."""
    xdg_config = Path.home() / ".config"
    return xdg_config / "lemonaid" / "config.toml"


def get_default_config() -> str:
    """Return the default config file contents."""
    return """\
# Lemonaid configuration

# Switch-handlers are auto-selected based on the notification's switch-source.
# No configuration needed for tmux/wezterm - they just work.

[wezterm]
# How to resolve pane from notification metadata
# Options: "tty" (match TTY to pane), "metadata" (use workspace/pane_id from metadata)
resolve_pane = "tty"
"""


@dataclass
class WeztermConfig:
    """Configuration for the WezTerm handler."""

    resolve_pane: str = "tty"  # "tty" or "metadata"


@dataclass
class TmuxSessionConfig:
    """Configuration for tmux session templates."""

    templates: dict[str, list[str]] = field(default_factory=dict)

    def get_template(self, name: str) -> list[str] | None:
        """Get a template by name."""
        return self.templates.get(name)


@dataclass
class KeybindingsConfig:
    """Configuration for TUI keybindings.

    Each command field is a string where each character is a valid key binding.
    For example, quit="qQ" means both 'q' and 'Q' will quit.

    The up_down field is a 2-character string: up, down.
    For vim: "kj", for Norman WASD-style: "ri".
    Empty string means use default arrow keys only.
    """

    quit: str = "q"
    select: str = ""  # Additional keys for selecting (Enter always works)
    refresh: str = "g"
    jump_unread: str = "u"
    mark_read: str = "m"
    archive: str = "a"
    rename: str = "r"
    history: str = "h"  # Toggle history view
    copy_resume: str = "c"  # Copy resume command to clipboard
    up_down: str = ""  # 2-char string: up, down (e.g., "kj" for vim)


@dataclass
class TuiConfig:
    """Configuration for the TUI."""

    transparent: bool = False  # Use ANSI colors for terminal transparency
    keybindings: KeybindingsConfig = field(default_factory=KeybindingsConfig)


@dataclass
class Config:
    """Lemonaid configuration."""

    handlers: dict[str, str] = field(default_factory=dict)
    wezterm: WeztermConfig = field(default_factory=WeztermConfig)
    tmux_session: TmuxSessionConfig = field(default_factory=TmuxSessionConfig)
    tui: TuiConfig = field(default_factory=TuiConfig)

    def get_handler(self, channel: str) -> str | None:
        """Get the handler for a channel, using pattern matching."""
        for pattern, handler in self.handlers.items():
            if fnmatch(channel, pattern):
                return handler
        return None


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from file, or return defaults."""
    if config_path is None:
        config_path = get_config_path()

    if not config_path.exists():
        return Config()

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        # Log warning but return defaults
        print(f"Warning: Could not load config from {config_path}: {e}")
        return Config()

    return _parse_config(data)


def _parse_config(data: dict[str, Any]) -> Config:
    """Parse config dict into Config object."""
    handlers = data.get("handlers", {})

    wezterm_data = data.get("wezterm", {})
    wezterm = WeztermConfig(
        resolve_pane=wezterm_data.get("resolve_pane", "tty"),
    )

    tmux_session_data = data.get("tmux-session", {})
    tmux_session = TmuxSessionConfig(
        templates=tmux_session_data.get("templates", {}),
    )

    tui_data = data.get("tui", {})
    keybindings_data = tui_data.get("keybindings", {})
    # Use dataclass defaults for any unspecified keybindings
    defaults = KeybindingsConfig()
    keybindings = KeybindingsConfig(
        **{
            field: keybindings_data.get(field, getattr(defaults, field))
            for field in defaults.__dataclass_fields__
        }
    )
    tui = TuiConfig(
        transparent=tui_data.get("transparent", False),
        keybindings=keybindings,
    )

    return Config(handlers=handlers, wezterm=wezterm, tmux_session=tmux_session, tui=tui)


def ensure_config_exists() -> Path:
    """Ensure the config file exists, creating with defaults if needed."""
    config_path = get_config_path()

    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(get_default_config())

    return config_path
