"""Scratch pane functionality for lemonaid.

Provides a toggleable "always-on" lma pane that can be shown/hidden
without restarting the TUI (avoiding startup latency).

Per-server state files in ~/.local/state/lemonaid/:
  tmux-scratch-<server>-pane    — pane ID (e.g. "%6"). Present = pane is alive.
  tmux-scratch-<server>-follow  — follow flag. "on" = follow active, empty = disabled.
                                  Missing = first run, bootstrap from config.
  tmux-scratch-<server>-height  — last known height in rows, for a top pane.
  tmux-scratch-<server>-width   — last known width in columns, for a left pane.
                                  Separate files: a top pane's rows and a left
                                  pane's columns are different quantities, so
                                  switching position keeps both.
  tmux-scratch-follow.sh        — shell hook script, generated once.
"""

import os
import subprocess
import sys
from pathlib import Path

from ..log import get_logger
from .navigation import get_state_path

_log = get_logger("tmux.scratch")

_SCRATCH_SESSION = "_lma_scratch"


def _get_server_name() -> str:
    """Get the tmux server name from TMUX env var.

    TMUX format: /path/to/socket,pid,pane_index
    Returns the socket basename (e.g., 'default' for the default server).
    """
    tmux_env = os.environ.get("TMUX", "")
    if tmux_env:
        socket_path = tmux_env.split(",")[0]
        return os.path.basename(socket_path)
    return "default"


def _state_path() -> Path:
    return get_state_path() / f"tmux-scratch-{_get_server_name()}-pane"


def _height_path() -> Path:
    return get_state_path() / f"tmux-scratch-{_get_server_name()}-height"


def _width_path() -> Path:
    return get_state_path() / f"tmux-scratch-{_get_server_name()}-width"


def _size_path(position: str) -> Path:
    return _width_path() if position == "left" else _height_path()


def _pane_size_format(position: str) -> str:
    return "#{pane_width}" if position == "left" else "#{pane_height}"


def _split_flag(position: str) -> str:
    """tmux join-pane axis flag. -b ("before") is top for -v, left for -h."""
    return "-h" if position == "left" else "-v"


def _get_pane_id() -> str | None:
    """Load the scratch pane ID from the state file."""
    path = _state_path()
    if not path.exists():
        return None

    pane_id = path.read_text().strip()
    return pane_id or None


def _save_pane_id(pane_id: str) -> None:
    """Save the scratch pane ID."""
    _state_path().write_text(pane_id)


def _current_size(pane_id: str, position: str) -> str:
    result = subprocess.run(
        ["tmux", "display-message", "-t", pane_id, "-p", _pane_size_format(position)],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def save_current_size(position: str) -> None:
    """Persist the pane's size along the axis its position splits.

    Only called on explicit user action (keybinding), never automatically.
    """
    pane_id = _get_pane_id()
    if not pane_id:
        return

    size = _current_size(pane_id, position)
    if size:
        _log.info("save_current_size: %s (%s)", size, position)
        _size_path(position).write_text(size)


def size_has_drifted(position: str) -> bool:
    """Whether the pane's current size differs from the saved one."""
    pane_id = _get_pane_id()
    if not pane_id:
        return False

    path = _size_path(position)
    saved = path.read_text().strip() if path.exists() else ""
    if not saved:
        return False

    try:
        return int(_current_size(pane_id, position)) != int(saved)
    except ValueError:
        return False


def _clear_state() -> None:
    """Clear scratch pane state. Follow hooks become no-ops until prefix+l."""
    path = _state_path()
    if path.exists():
        path.unlink()


def _follow_path() -> Path:
    return get_state_path() / f"tmux-scratch-{_get_server_name()}-follow"


def is_follow_enabled() -> bool:
    """Check if follow mode is active for this tmux server."""
    path = _follow_path()
    if not path.exists():
        return False

    return path.read_text().strip() == "on"


def set_follow_enabled(enabled: bool) -> None:
    """Set follow mode for this tmux server. Empty file = disabled."""
    _follow_path().write_text("on" if enabled else "")


def bootstrap_follow(config_default: bool) -> None:
    """Create the follow file from config if it doesn't exist yet.

    Called on first scratch pane creation for this server.
    """
    path = _follow_path()
    if not path.exists():
        path.write_text("on" if config_default else "")


def _pane_exists(pane_id: str) -> bool:
    """Check if the scratch pane still exists and is ours.

    Verifies the pane exists AND has our marker option set. This prevents
    latching onto a pane with the same ID that happens to exist elsewhere.
    """
    result = subprocess.run(
        ["tmux", "display-message", "-t", pane_id, "-p", "#{@lemonaid_scratch}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False

    # Check that our marker is set
    return result.stdout.strip() == "1"


def _mark_pane(pane_id: str) -> None:
    """Mark a pane as our scratch pane using a tmux option."""
    subprocess.run(
        ["tmux", "set-option", "-p", "-t", pane_id, "@lemonaid_scratch", "1"],
        capture_output=True,
    )


def _get_pane_window(pane_id: str) -> str | None:
    """Get the window ID that contains a pane."""
    result = subprocess.run(
        ["tmux", "display-message", "-t", pane_id, "-p", "#{window_id}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _get_current_window() -> str | None:
    """Get the current window ID."""
    result = subprocess.run(
        ["tmux", "display-message", "-p", "#{window_id}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _session_exists() -> bool:
    """Check if the scratch tmux session exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", _SCRATCH_SESSION],
        capture_output=True,
    )
    return result.returncode == 0


def _get_session_pane() -> str | None:
    """Get the pane ID of the first pane in the scratch session."""
    result = subprocess.run(
        ["tmux", "list-panes", "-t", _SCRATCH_SESSION, "-F", "#{pane_id}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip().split("\n")[0]
    return None


def _create_pane() -> str:
    """Create the scratch pane with lma running. Returns pane_id."""
    # Clean up legacy state files from pre-0.12
    for name in (
        f"scratch-pane-{_get_server_name()}.json",
        f"scratch-pane-{_get_server_name()}",
    ):
        legacy = get_state_path() / name
        if legacy.exists():
            legacy.unlink()

    # Check if session already exists (recovery: state file lost but session exists)
    if _session_exists():
        pane_id = _get_session_pane()
        if pane_id:
            _mark_pane(pane_id)
            _save_pane_id(pane_id)
            return pane_id

    # Get current window dimensions to size the detached session properly
    # (otherwise detached sessions get tiny default dimensions)
    size_result = subprocess.run(
        ["tmux", "display-message", "-p", "#{window_width} #{window_height}"],
        capture_output=True,
        text=True,
    )
    width, height = "200", "50"  # fallback defaults
    if size_result.returncode == 0:
        parts = size_result.stdout.strip().split()
        if len(parts) == 2:
            width, height = parts

    # Create a new session with lma in scratch mode
    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            _SCRATCH_SESSION,
            "-x",
            width,
            "-y",
            height,
            "-n",
            "lma",
            "lma",
            "--scratch",
        ],
        check=True,
    )
    # Prevent tmux from auto-renaming the window
    subprocess.run(
        ["tmux", "set-window-option", "-t", _SCRATCH_SESSION, "automatic-rename", "off"],
        capture_output=True,
    )

    result = subprocess.run(
        ["tmux", "list-panes", "-t", _SCRATCH_SESSION, "-F", "#{pane_id}"],
        capture_output=True,
        text=True,
        check=True,
    )
    pane_id = result.stdout.strip()
    _mark_pane(pane_id)
    _save_pane_id(pane_id)
    return pane_id


def _show(pane_id: str, size: str, position: str, target_pane: str | None = None) -> bool:
    """Join the scratch pane into the current window, above or left of it."""
    cmd = ["tmux", "join-pane", _split_flag(position), "-b", "-l", size, "-s", pane_id]
    if target_pane:
        cmd.extend(["-t", target_pane])
    if subprocess.run(cmd, capture_output=True).returncode != 0:
        return False

    # The follow hook reads this file for its size, so a position being used for
    # the first time has to record one - otherwise the hook falls back to the
    # default compiled into it when follow was enabled.
    path = _size_path(position)
    if not path.exists():
        path.write_text(size)

    return True


def _ensure_scratch_session() -> None:
    """Recreate the scratch session if it was destroyed.

    When join-pane moves the scratch pane into the user's session,
    _lma_scratch loses its last window and tmux destroys it. We need
    it back so break-pane has somewhere to send the pane.
    """
    if not _session_exists():
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", _SCRATCH_SESSION, "-n", "_placeholder", "sh"],
            capture_output=True,
        )


def _hide(pane_id: str) -> bool:
    """Break the scratch pane back to the scratch session."""
    _ensure_scratch_session()
    result = subprocess.run(
        ["tmux", "break-pane", "-d", "-s", pane_id, "-t", f"{_SCRATCH_SESSION}:"],
        capture_output=True,
    )
    if result.returncode != 0:
        return False

    # Kill the placeholder window if one was created — break-pane already
    # added a real window for the scratch pane.
    subprocess.run(
        ["tmux", "kill-window", "-t", f"{_SCRATCH_SESSION}:_placeholder"],
        capture_output=True,
    )
    return True


def _select_pane(pane_id: str) -> bool:
    """Select (focus) a pane."""
    result = subprocess.run(
        ["tmux", "select-pane", "-t", pane_id],
        capture_output=True,
    )
    return result.returncode == 0


def _get_current_pane() -> str | None:
    """Get the current pane ID."""
    result = subprocess.run(
        ["tmux", "display-message", "-p", "#{pane_id}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _create_and_show(size: str, position: str) -> str:
    """Create a fresh scratch pane and show it."""
    # Capture target pane BEFORE creating new session (tmux context can change)
    target_pane = _get_current_pane()

    _clear_state()
    if _session_exists():
        subprocess.run(
            ["tmux", "kill-session", "-t", _SCRATCH_SESSION],
            capture_output=True,
        )
    pane_id = _create_pane()
    _show(pane_id, size, position, target_pane)
    return "created"


def ensure_scratch(size: str = "10", position: str = "top") -> str:
    """Ensure the scratch pane is visible in the current window.

    Like toggle, but never hides — only creates or shows.
    Returns 'shown', 'created', or 'already_visible'.
    """
    current_pane = _get_current_pane()
    pane_id = _get_pane_id()

    if pane_id is None or not _pane_exists(pane_id):
        return _create_and_show(size, position)

    current_window = _get_current_window()
    pane_window = _get_pane_window(pane_id)

    if pane_window == current_window:
        return "already_visible"

    if not _show(pane_id, size, position, current_pane):
        return _create_and_show(size, position)

    return "shown"


def _follow_script_path() -> Path:
    return get_state_path() / "tmux-scratch-follow.sh"


def _write_follow_script(size: str = "10", position: str = "top") -> Path:
    """Write the follow hook script to disk.

    Pure shell — reads the pane ID from the state file, checks if
    it's already in the current window, and joins it if not.  ~5ms
    on the hot path (already visible).
    """
    script_path = _follow_script_path()
    state_dir = str(get_state_path())
    dimension = "width" if position == "left" else "height"
    axis = _split_flag(position)
    # Parse tmux server name from $TMUX the same way the Python code does
    script_path.write_text(
        f"""#!/bin/sh
# lemonaid scratch-follow hook — do not edit, regenerated by lemonaid
server=$(basename "$(echo "$TMUX" | cut -d, -f1)")
[ -n "$server" ] || server=default
dir={state_dir}

# Is follow enabled for this server?
grep -q on "$dir/tmux-scratch-$server-follow" 2>/dev/null || exit 0

# Is there a pane to show?
pane=$(cat "$dir/tmux-scratch-$server-pane" 2>/dev/null)
[ -n "$pane" ] || exit 0

# Already in this window?
cur=$(tmux display -p '#{{window_id}}')
tgt=$(tmux display -t "$pane" -p '#{{window_id}}' 2>/dev/null) || exit 0
[ "$cur" = "$tgt" ] && exit 0

size=$(cat "$dir/tmux-scratch-$server-{dimension}" 2>/dev/null)
[ -n "$size" ] || size={size}

cur_pane=$(tmux display -p '#{{pane_id}}')
tmux join-pane {axis} -b -l "$size" -s "$pane" 2>/dev/null
tmux select-pane -t "$cur_pane" 2>/dev/null
exit 0
"""
    )
    script_path.chmod(0o755)
    return script_path


def _check_tmux_conf_hooks() -> bool:
    """Check if something that looks like the follow hooks is in .tmux.conf."""
    tmux_conf = Path.home() / ".tmux.conf"
    if not tmux_conf.exists():
        return False

    return "scratch-follow" in tmux_conf.read_text()


def set_follow(size: str = "10", position: str = "top", enable: bool = True) -> str:
    """Enable or disable follow mode for this tmux server.

    When enabled, installs tmux hooks for the current server session
    and generates the follow script. Warns if .tmux.conf doesn't have
    the hooks (so follow won't persist across tmux restarts).
    """
    set_follow_enabled(enable)

    if enable:
        ensure_scratch(size, position)
        _write_follow_script(size, position)
        _install_hooks()

        if not _check_tmux_conf_hooks():
            script = _follow_script_path()
            print(
                f"\nFollow enabled for this tmux server session.\n"
                f"To persist across tmux restarts, add these to .tmux.conf:\n\n"
                f"  set-hook -g after-select-window[100] 'run-shell -b \"{script}\"'\n"
                f"  set-hook -g session-window-changed[100] 'run-shell -b \"{script}\"'\n"
                f"  set-hook -g client-session-changed[100] 'run-shell -b \"{script}\"'\n",
                file=sys.stderr,
            )

        return "follow enabled"

    return "follow disabled"


def _install_hooks() -> None:
    """Install the tmux hooks that call the follow script."""
    script = _follow_script_path()
    for hook in ("after-select-window", "session-window-changed", "client-session-changed"):
        subprocess.run(
            ["tmux", "set-hook", "-g", f"{hook}[100]", f"run-shell -b '{script}'"],
            capture_output=True,
        )


def toggle_scratch(size: str = "10", position: str = "top", follow_default: bool = False) -> str:
    """Toggle the scratch lma pane. Returns 'shown', 'hidden', 'selected', or 'created'.

    In follow mode, the pane is never hidden via toggle — use q in lma to dismiss.
    follow_default is the config value, used to bootstrap the follow file on first run.
    """
    bootstrap_follow(follow_default)
    follow = is_follow_enabled()

    current_pane = _get_current_pane()
    pane_id = _get_pane_id()

    if pane_id is None or not _pane_exists(pane_id):
        return _create_and_show(size, position)

    current_window = _get_current_window()
    pane_window = _get_pane_window(pane_id)

    if pane_window == current_window:
        if current_pane == pane_id:
            if follow:
                # Focus the next pane (the main content pane below)
                subprocess.run(
                    ["tmux", "select-pane", "-t", ":.+"],
                    capture_output=True,
                )
                return "defocused"

            if not _hide(pane_id):
                return _create_and_show(size, position)

            return "hidden"
        else:
            if not _select_pane(pane_id):
                return _create_and_show(size, position)

            return "selected"
    else:
        if not _show(pane_id, size, position, current_pane):
            return _create_and_show(size, position)

        return "shown"
