"""Configuration management for lemonaid."""

import datetime as dt
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from . import auto_read, keys, watch_config
from .inbox import context_use, snooze_time
from .usage import settings


def get_config_path() -> Path:
    """The config file, `LEMONAID_CONFIG` overriding the XDG default."""
    if override := os.environ.get("LEMONAID_CONFIG"):
        return Path(override).expanduser()

    xdg_config = Path.home() / ".config"
    return xdg_config / "lemonaid" / "config.toml"


def get_default_config() -> str:
    """Return the default config file contents."""
    return """\
# Lemonaid configuration

# Switch-handlers are auto-selected based on the notification's switch-source.
# No configuration needed for tmux/wezterm - they just work.

# Session templates are named after the harness their lemon window starts.
# `--harness NAME` picks one; without it, `default` is used.
# [tmux-session.templates]
# claude = ["emacsclient -nw .", "claude", ""]
# codex = ["emacsclient -nw .", "codex --no-daemon", ""]
# default = "claude"

[tmux-window]
# Apps hidden behind an interpreter whose names should replace the directory.
named_processes = []

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
    # 0-based template window whose command accepts an initial prompt. None
    # follows resume_window, since both normally identify the lemon window.
    harness_window: int | None = None
    # Extra directories a Codex lemon may write, beyond the lemonaid database and
    # state directories (review-doc folders, for instance).
    codex_writable_roots: tuple[Path, ...] = ()
    # Where the scratch pane sits: "top" or "left".
    scratch_position: str = "left"
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
class TmuxWindowConfig:
    """Configuration for tmux status-line window names."""

    # Entrypoints hidden behind an interpreter process. Once found in the pane
    # process tree, these replace the directory with the configured name.
    named_processes: tuple[str, ...] = ()


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
    search: str = "/"  # Search the inbox, or filter history
    copy_resume: str = "c"  # Copy resume command to clipboard
    resume_detached: str = "R"  # Resume a detached session from the inbox
    tmux_resume: str = "T"  # Spawn tmux session around a history entry
    brief: str = "b"  # Show the session's brief in a tmux popup
    pin: str = "p"  # Pin a session to a fixed place in the list, or unpin it
    # Unlike the fields above, these name one key each rather than a set of
    # single-character alternatives, so that they can be a named key or carry a modifier.
    brief_key: str = "tab"  # A second key for brief
    move_pin_up: str = "shift+up"
    move_pin_down: str = "shift+down"
    first: str = "ctrl+a"  # The top row of the list; Home always works too
    last: str = "ctrl+e"  # The bottom row of the list; End always works too
    save_size: str = "H"  # Save the scratch pane size (follow mode only)
    flip_position: str = "f"  # Move the scratch pane between top and left
    fold: str = "w"  # Show or hide the sessions folded at the bottom of the list
    notes: str = "N"  # Show or hide the [tui] notes file under the sessions
    # In a brief view, the questions under what a lemon needs from you.
    question_previous: str = "["
    question_next: str = "]"
    answer: str = "a"  # Type an answer, sent to the lemon with `lemonaid tell`
    answer_yes: str = "Y"  # Immediately answer the selected question "Yes, approved"
    more_detail: str = "d"  # Ask the lemon to rewrite the selected question
    # Digits 1-9 then 0 switch to that row of the list, counting from the top.
    jump_by_number: bool = True
    up_down: str = ""  # 2-char string: up, down (e.g., "kj" for vim)


# What a card's second line can show, and a column row's directory column.
CARD_FIELDS = ("time", "age", "project", "branch", "cwd")


@dataclass
class TuiConfig:
    """Configuration for the TUI."""

    transparent: bool = False  # Use ANSI colors for terminal transparency
    refresh_interval: float = 0.33  # Seconds between TUI refreshes
    card_unread_style: str = "dot"  # "dot" or a full-width "bar"
    # The second line of a card, in order; any of CARD_FIELDS.
    card_fields: tuple[str, ...] = ("time", "project", "branch")
    brief_status: bool = False
    brief_stale_hours: float = 6.0
    # Show a mid-turn lemon as working, whatever its brief's Status says.
    mid_turn_working: bool = False
    # Show each attached brief's short name after its session name.
    brief_names_in_inbox: bool = False
    project_name_colors: bool = False
    # Override the selected inbox row background. Otherwise dark themes use a deeper blue.
    active_row_color: str | None = None
    # Brief statuses whose read, unpinned sessions fold into one group at the
    # bottom of the list. Empty folds nothing.
    fold_statuses: list[str] = field(default_factory=list)
    # The scratch pane's title bar and bottom edge while it will receive keys.
    focus_color: str = "#2bd9cf"
    # A Markdown file shown under the sessions when they are cards. None shows nothing.
    notes: Path | None = None
    keybindings: KeybindingsConfig = field(default_factory=KeybindingsConfig)
    # Override the label shown for each backend in the TUI.
    # Keys are channel prefixes (claude, codex, openclaw, opencode); values are display strings.
    # Unset backends default to their channel prefix.
    backend_labels: dict[str, str] = field(default_factory=dict)
    # Where each harness or model counts as 100% context used; unset is its whole window.
    context_threshold: dict[str, context_use.Threshold] = field(default_factory=dict)


@dataclass
class BriefConfig:
    """Configuration for showing briefs."""

    # Shell command printing a PR's state (open, draft, merged, closed) for
    # `{ref}`, a PR number or URL, run in the lemon's place. Unset shows no state.
    pr_state: str = ""
    # Shell command printing a PR's URL for `{ref}`, a PR number, run in the
    # caller's directory. Lets `brief pr add` take a number instead of a URL.
    pr_url: str = ""
    # Shell command printing a new lemon's name, the part of its Lemon-ID after
    # the dot. Unset names it with a random two-word WordyBin.
    name: str = ""
    # Obsidian vault roots, expanded. A bare `.md` path under one becomes an
    # `obsidian://` link.
    vaults: tuple[Path, ...] = ()


@dataclass
class InboxConfig:
    """Configuration for the inbox rows themselves."""

    # A completed turn whose final message matches one of these, from its
    # start, leaves its session read instead of unread.
    auto_read: tuple[re.Pattern[str], ...] = ()
    # A lemon's first turn at or after this local time each day is told the date.
    day_starts: dt.time = dt.time(6, 0)
    # A snooze of a day or more, and the 'morning' snooze, ends at this local time.
    snooze_day_starts: dt.time = snooze_time.DEFAULT_DAY_START
    # The snooze picker's presets, in `inbox snooze` syntax.
    snooze_presets: tuple[str, ...] = snooze_time.DEFAULT_PRESETS
    # A program lma keeps running to order and fold its list; see docs/arrange.md.
    arrange: str = ""
    # Let the arranger fold an unread row, which otherwise stays in the list.
    arrange_may_fold_unread: bool = False


@dataclass
class OpenclawConfig:
    """Configuration for OpenClaw integration."""

    remote_host: str | None = None  # SSH host for remote session files


@dataclass
class BackendConfig:
    """Configuration for a lemon backend (claude, codex, etc)."""

    resume_command: str = ""
    submit_key: str = "Enter"


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
    name: str = ""  # the project's name on brief cards; the root's directory name when unset
    list: str = ""  # candidate directories, one absolute path per line
    path_of: str = ""  # {key} -> the directory for that key
    create: str = ""  # acquire a directory for {key}
    destroy: str = ""  # release the directory for {key}
    inspect: str = ""  # one short display line about {dir}
    project_name: str = ""  # {dir} -> one project label for inbox rows
    # Keys that must never be destroyed, no matter how they are asked for. A
    # worktree repo usually has one directory the others are branched from, and
    # losing it is not the sort of mistake a --force flag should be able to make.
    protected: tuple[str, ...] = ("main", "master")
    open_prs: str = ""  # open PRs, one '<branch> <number>' line each

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
    tmux_window: TmuxWindowConfig = field(default_factory=TmuxWindowConfig)
    tui: TuiConfig = field(default_factory=TuiConfig)
    brief: BriefConfig = field(default_factory=BriefConfig)
    inbox: InboxConfig = field(default_factory=InboxConfig)
    openclaw: OpenclawConfig = field(default_factory=OpenclawConfig)
    backends: dict[str, BackendConfig] = field(default_factory=dict)
    places: PlacesConfig = field(default_factory=PlacesConfig)
    watch: watch_config.WatchConfig = field(default_factory=watch_config.WatchConfig)
    usage: settings.UsageConfig = field(default_factory=settings.UsageConfig)

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


def _card_fields(raw: object) -> tuple[str, ...]:
    """`[tui] card_fields`, reporting and skipping any name it doesn't know."""
    default = TuiConfig.card_fields
    if raw is None:
        return default
    if not isinstance(raw, list):
        print(
            f"Warning: [tui] card_fields must be a list of {', '.join(CARD_FIELDS)}",
            file=sys.stderr,
        )
        return default

    for name in raw:
        if name not in CARD_FIELDS:
            print(
                f"Warning: [tui] card_fields: ignoring {name!r}, not one of {', '.join(CARD_FIELDS)}",
                file=sys.stderr,
            )
    return tuple(dict.fromkeys(name for name in raw if name in CARD_FIELDS))


def _notes(raw: object) -> Path | None:
    """`[tui] notes`, reporting anything that is not a path."""
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        print(
            f"Warning: [tui] notes must be a file path, not {type(raw).__name__}", file=sys.stderr
        )
        return None
    return Path(raw).expanduser()


def _vaults(raw: object) -> tuple[Path, ...]:
    """`[brief] vaults`, reporting and skipping anything that is not a directory."""
    if not isinstance(raw, list):
        if raw is not None:
            print(
                f"Warning: [brief] vaults must be a list of directories, not {type(raw).__name__}",
                file=sys.stderr,
            )
        return ()

    for root in raw:
        if not isinstance(root, str) or not root:
            print(f"Warning: [brief] vaults: ignoring {root!r}", file=sys.stderr)
    return tuple(Path(root).expanduser() for root in raw if isinstance(root, str) and root)


def _paths(raw: object) -> tuple[Path, ...]:
    """A list of path strings with `~` expanded; anything else is reported and dropped."""
    entries = raw if isinstance(raw, list) else [raw]
    for entry in entries:
        if not isinstance(entry, str) or not entry:
            print(
                f"lemonaid: [tmux-session] codex_writable_roots: ignoring {entry!r}",
                file=sys.stderr,
            )

    return tuple(Path(e).expanduser() for e in entries if isinstance(e, str) and e)


def _templates(raw: dict[str, Any]) -> dict[str, list[str]]:
    """`[tmux-session.templates]`, with a string `default` resolved to the template it names.

    A `default` naming a missing template, or itself, is reported and dropped, so
    that a launch without `--harness` fails rather than starting the wrong lemon.
    """
    templates = {name: windows for name, windows in raw.items() if isinstance(windows, list)}
    alias = raw.get("default")
    if not isinstance(alias, str):
        return templates

    if alias == "default" or alias not in templates:
        reason = "names itself" if alias == "default" else "names no template"
        print(
            f"Error: [tmux-session.templates] default = {alias!r} {reason};"
            f" templates are: {', '.join(templates) or '(none)'}",
            file=sys.stderr,
        )
        return templates

    return {**templates, "default": templates[alias]}


def _local_time(key: str, raw: object, default: dt.time) -> dt.time:
    """A TOML local time or an "HH:MM" string; anything else, an offset included, is reported and gives *default*."""
    if raw is None:
        return default

    try:
        parsed = raw if isinstance(raw, dt.time) else dt.time.fromisoformat(str(raw))
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is not None:
        print(f"lemonaid: [inbox] {key}: ignoring {raw!r}, not a local HH:MM", file=sys.stderr)
        return default

    return parsed


def _snooze_presets(raw: object) -> tuple[str, ...]:
    """The presets `snooze_time` can read; others are reported, and none at all gives the defaults."""
    if raw is None:
        return InboxConfig.snooze_presets

    entries = raw if isinstance(raw, list) else [raw]
    presets = tuple(
        entry.strip()
        for entry in entries
        if isinstance(entry, str)
        and snooze_time.parse_wake(entry, 0.0, snooze_time.DEFAULT_DAY_START) is not None
    )
    for entry in entries:
        if not isinstance(entry, str) or entry.strip() not in presets:
            print(f"lemonaid: [inbox] snooze_presets: ignoring {entry!r}", file=sys.stderr)

    return presets or InboxConfig.snooze_presets


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
        templates=_templates(tmux_session_data.get("templates", {})),
        resume_window=tmux_session_data.get("resume_window", 0),
        harness_window=tmux_session_data.get("harness_window"),
        codex_writable_roots=_paths(tmux_session_data.get("codex_writable_roots", [])),
        scratch_position=tmux_session_data.get(
            "scratch_position", tmux_session_defaults.scratch_position
        ),
        scratch_height=tmux_session_data.get(
            "scratch_height", tmux_session_defaults.scratch_height
        ),
        scratch_width=tmux_session_data.get("scratch_width", tmux_session_defaults.scratch_width),
        follow_scratch=tmux_session_data.get("follow_scratch", False),
    )

    tmux_window_data = data.get("tmux-window", {})
    named_processes = tmux_window_data.get("named_processes", ())
    tmux_window = TmuxWindowConfig(
        named_processes=tuple(
            name.strip() for name in named_processes if isinstance(name, str) and name.strip()
        )
        if isinstance(named_processes, list)
        else (),
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
    for warning in keys.conflicts(keybindings):
        print(f"Warning: [tui.keybindings] {warning}", file=sys.stderr)
    tui = TuiConfig(
        transparent=tui_data.get("transparent", False),
        refresh_interval=tui_data.get("refresh_interval", 0.33),
        card_unread_style=tui_data.get("card_unread_style", "dot"),
        card_fields=_card_fields(tui_data.get("card_fields")),
        brief_status=tui_data.get("brief_status", False),
        brief_stale_hours=tui_data.get("brief_stale_hours", 6.0),
        mid_turn_working=tui_data.get("mid_turn_working", False),
        brief_names_in_inbox=tui_data.get("brief_names_in_inbox", False),
        project_name_colors=tui_data.get("project_name_colors", False),
        active_row_color=tui_data.get("active_row_color"),
        fold_statuses=list(tui_data.get("fold_statuses", [])),
        focus_color=tui_data.get("focus_color", "#2bd9cf"),
        notes=_notes(tui_data.get("notes")),
        keybindings=keybindings,
        backend_labels=tui_data.get("backend_labels", {}),
        context_threshold=context_use.parse_thresholds(tui_data.get("context_threshold")),
    )

    brief_data = data.get("brief", {})
    brief = BriefConfig(
        pr_state=brief_data.get("pr_state", ""),
        pr_url=brief_data.get("pr_url", ""),
        name=brief_data.get("name", ""),
        vaults=_vaults(brief_data.get("vaults")),
    )

    inbox_data = data.get("inbox", {})
    inbox = InboxConfig(
        auto_read=auto_read.compile_patterns(inbox_data.get("auto_read")),
        day_starts=_local_time("day_starts", inbox_data.get("day_starts"), InboxConfig.day_starts),
        snooze_day_starts=_local_time(
            "snooze_day_starts",
            inbox_data.get("snooze_day_starts"),
            InboxConfig.snooze_day_starts,
        ),
        snooze_presets=_snooze_presets(inbox_data.get("snooze_presets")),
        arrange=inbox_data.get("arrange", ""),
        arrange_may_fold_unread=inbox_data.get("arrange_may_fold_unread", False),
    )

    openclaw_data = data.get("openclaw", {})
    openclaw = OpenclawConfig(
        remote_host=openclaw_data.get("remote_host"),
    )

    backends_data = data.get("backends", {})
    backends = {}
    for name, bd in backends_data.items():
        if not isinstance(bd, dict):
            continue

        submit_key = bd.get("submit_key", "Enter")
        if submit_key not in ("Enter", "C-Enter"):
            print(
                f"Warning: [backends.{name}] submit_key must be Enter or C-Enter",
                file=sys.stderr,
            )
            submit_key = "Enter"
        backends[name] = BackendConfig(
            resume_command=bd.get("resume_command", ""), submit_key=submit_key
        )

    places_data = data.get("places", {})
    places = PlacesConfig(
        protected_sessions=tuple(places_data.get("protected_sessions", ())),
        roots=[
            PlaceRoot(
                path=Path(rd["path"]).expanduser(),
                name=rd.get("name", ""),
                list=rd.get("list", ""),
                path_of=rd.get("path_of", ""),
                create=rd.get("create", ""),
                destroy=rd.get("destroy", ""),
                inspect=rd.get("inspect", ""),
                open_prs=rd.get("open_prs", ""),
                project_name=rd.get("project_name", ""),
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
        tmux_window=tmux_window,
        tui=tui,
        brief=brief,
        inbox=inbox,
        openclaw=openclaw,
        backends=backends,
        places=places,
        watch=watch_config.parse(data.get("watch", {})),
        usage=settings.parse(data.get("usage", {})),
    )


def ensure_config_exists() -> Path:
    """Ensure the config file exists, creating with defaults if needed."""
    config_path = get_config_path()

    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(get_default_config())

    return config_path
