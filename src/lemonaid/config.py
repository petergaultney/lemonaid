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
    # 0-based index into the template window list: which window to replace
    # with the resume command when spawning a session from history.
    resume_window: int = 0
    # Where the scratch pane sits: "top" or "left".
    scratch_position: str = "top"
    # Size of the scratch pane along the axis it splits. A top pane is measured
    # in rows and a left one in columns, so the two are stored separately -
    # switching position keeps the size you chose for each.
    scratch_height: str = "10"
    scratch_width: str = "45"
    # When true, the scratch pane follows across window/session switches.
    follow_scratch: bool = False

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
    mark_unread: str = "M"
    archive: str = "a"
    rename: str = "r"
    snooze: str = "s"  # Snooze a session out of the inbox for a while
    snoozed_list: str = "S"  # Toggle the snoozed-sessions view
    undo: str = "z"  # Undo the last inbox state change
    history: str = "h"  # Toggle history view
    copy_resume: str = "c"  # Copy resume command to clipboard
    tmux_resume: str = "T"  # Spawn tmux session around a history entry
    save_size: str = "H"  # Save the scratch pane size (follow mode only)
    flip_position: str = "f"  # Move the scratch pane between top and left
    up_down: str = ""  # 2-char string: up, down (e.g., "kj" for vim)


@dataclass
class TuiConfig:
    """Configuration for the TUI."""

    transparent: bool = False  # Use ANSI colors for terminal transparency
    refresh_interval: float = 0.33  # Seconds between TUI refreshes
    keybindings: KeybindingsConfig = field(default_factory=KeybindingsConfig)
    # Override the label shown for each backend in the TUI.
    # Keys are channel prefixes (claude, codex, openclaw, opencode); values are display strings.
    # Unset backends default to their channel prefix.
    backend_labels: dict[str, str] = field(default_factory=dict)


@dataclass
class OpenclawConfig:
    """Configuration for OpenClaw integration."""

    remote_host: str | None = None  # SSH host for remote session files


@dataclass
class BackendConfig:
    """Configuration for a lemon backend (claude, codex, etc)."""

    resume_command: str = ""


@dataclass(frozen=True)
class PlaceRoot:
    """Shell commands for acquiring and releasing directories under one root.

    lemonaid knows about directories and terminals; it does not know what a
    worktree is. A root that manages its directories with some external tool
    declares that tool here, and lemonaid substitutes and runs it.

    `{key}` is opaque - whatever the configured tool names directories by. For a
    git-worktree tool it is a branch name; lemonaid neither knows nor checks
    that. `{dir}` is an absolute path.

    Every command is optional. Unset means that capability no-ops for this root,
    which is how a plain clone (nothing to list, create, or destroy) coexists
    with a worktree repo.
    """

    path: Path
    list: str = ""  # candidate directories, one absolute path per line
    path_of: str = ""  # {key} -> the directory for that key
    create: str = ""  # acquire a directory for {key}
    destroy: str = ""  # release the directory for {key}
    inspect: str = ""  # one short display line about {dir}
    # Keys that must never be destroyed, no matter how they are asked for. A
    # worktree repo usually has one directory the others are branched from, and
    # losing it is not the sort of mistake a --force flag should be able to make.
    protected: tuple[str, ...] = ("main", "master")

    def is_protected(self, key: str) -> bool:
        return key in self.protected

    def has_namespace(self) -> bool:
        """Whether keys mean anything here.

        Without a way to either list directories or resolve one from a key, a
        root has no vocabulary of its own - a name handed to it could not have
        referred to a directory it manages. Such a root exists so `place list`
        reports its directory; it does not claim the names used inside it.
        """
        return bool(self.list or self.path_of)


@dataclass
class PlacesConfig:
    roots: list[PlaceRoot] = field(default_factory=list)
    # Sessions that must never be torn down. Separate from a root's `protected`
    # keys: that guards a directory, this guards a session, and a long-lived
    # catchall session often isn't tied to any one managed directory.
    protected_sessions: tuple[str, ...] = ()

    def is_protected_session(self, session: str) -> bool:
        return session in self.protected_sessions

    def root_for(self, directory: str | Path) -> PlaceRoot | None:
        """The configured root that *directory* lives under, innermost first."""
        resolved = Path(directory).expanduser().resolve()
        return max(
            (root for root in self.roots if resolved == root.path or root.path in resolved.parents),
            key=lambda root: len(root.path.parts),
            default=None,
        )

    def namespaced_root_for(self, directory: str | Path) -> PlaceRoot | None:
        """The root whose key vocabulary applies in *directory*, if any.

        This decides how a name is read: inside such a root a name is a key, and
        failing to resolve one means create-or-typo. Outside every one of them,
        no root could have meant it, so it is free to mean something else.
        """
        root = self.root_for(directory)
        return root if root is not None and root.has_namespace() else None


@dataclass
class Config:
    """Lemonaid configuration."""

    handlers: dict[str, str] = field(default_factory=dict)
    wezterm: WeztermConfig = field(default_factory=WeztermConfig)
    tmux_session: TmuxSessionConfig = field(default_factory=TmuxSessionConfig)
    tui: TuiConfig = field(default_factory=TuiConfig)
    openclaw: OpenclawConfig = field(default_factory=OpenclawConfig)
    backends: dict[str, BackendConfig] = field(default_factory=dict)
    places: PlacesConfig = field(default_factory=PlacesConfig)

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
    tmux_session_defaults = TmuxSessionConfig()
    tmux_session = TmuxSessionConfig(
        templates=tmux_session_data.get("templates", {}),
        resume_window=tmux_session_data.get("resume_window", 0),
        scratch_position=tmux_session_data.get(
            "scratch_position", tmux_session_defaults.scratch_position
        ),
        scratch_height=tmux_session_data.get(
            "scratch_height", tmux_session_defaults.scratch_height
        ),
        scratch_width=tmux_session_data.get("scratch_width", tmux_session_defaults.scratch_width),
        follow_scratch=tmux_session_data.get("follow_scratch", False),
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
        refresh_interval=tui_data.get("refresh_interval", 0.33),
        keybindings=keybindings,
        backend_labels=tui_data.get("backend_labels", {}),
    )

    openclaw_data = data.get("openclaw", {})
    openclaw = OpenclawConfig(
        remote_host=openclaw_data.get("remote_host"),
    )

    backends_data = data.get("backends", {})
    backends = {
        name: BackendConfig(resume_command=bd.get("resume_command", ""))
        for name, bd in backends_data.items()
        if isinstance(bd, dict)
    }

    places_data = data.get("places", {})
    places = PlacesConfig(
        protected_sessions=tuple(places_data.get("protected_sessions", ())),
        roots=[
            PlaceRoot(
                path=Path(rd["path"]).expanduser(),
                list=rd.get("list", ""),
                path_of=rd.get("path_of", ""),
                create=rd.get("create", ""),
                destroy=rd.get("destroy", ""),
                inspect=rd.get("inspect", ""),
                protected=tuple(rd["protected"]) if "protected" in rd else PlaceRoot.protected,
            )
            for rd in places_data.get("roots", [])
            if isinstance(rd, dict) and rd.get("path")
        ],
    )

    return Config(
        handlers=handlers,
        wezterm=wezterm,
        tmux_session=tmux_session,
        tui=tui,
        openclaw=openclaw,
        backends=backends,
        places=places,
    )


def ensure_config_exists() -> Path:
    """Ensure the config file exists, creating with defaults if needed."""
    config_path = get_config_path()

    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(get_default_config())

    return config_path
