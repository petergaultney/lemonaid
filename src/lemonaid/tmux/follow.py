"""The follow hook: what puts the scratch pane in the window you switched to.

It runs inside the tmux server, as `if-shell -F` and `run-shell -C`, with no
shell process. That is what makes it correct rather than merely fast. One
switch fires two hooks (the session's window changed, and the client's session
changed), and hooks run one after another in the server - so the second sees
what the first did. Two background shells each saw the pane absent and both
joined it, and a pane joined twice into one window comes out at whatever width
the second split left it.

The pane is swapped, not moved. Every window it has left keeps a placeholder
pane in its slot - a bare `sleep` - so the window's own panes never change size
when the scratch pane comes or goes. Moving it meant the window you were
returning to was full width until the hook ran, and its program repainted in
front of you. A window it has never visited gets a placeholder split in first,
so that one visit is the only time the window's layout changes.

Everything the hook reads is a tmux option, which the server expands without
leaving the process. The files in the state directory remain the record that
survives a server restart; scratch.py writes both.
"""

import subprocess

# The saved size is the size. It yields only when the client cannot hold it and
# still leave the main pane this much: a sidebar is a character count, and a
# bigger font should cost the window's own panes columns, not the sidebar.
MIN_MAIN = {"left": 40, "top": 10}

FOLLOW_OPTION = "@lemonaid_follow"  # "on" or "off"
PANE_OPTION = "@lemonaid_scratch_pane"  # the pane to follow with; unset while parked
POSITION_OPTION = "@lemonaid_scratch_position"  # "left" or "top"
WIDTH_OPTION = "@lemonaid_scratch_width"  # columns, for a left pane
HEIGHT_OPTION = "@lemonaid_scratch_height"  # rows, for a top pane
MARKER_OPTION = "@lemonaid_scratch"  # set on the pane itself; how it is found again

# Recognised by its start command rather than an option: an option could only be
# set after the split, and the hook has to find the pane in the same breath.
PLACEHOLDER_COMMAND = ("env", "LEMONAID_PLACEHOLDER=1", "sleep", "2147483647")
_PLACEHOLDER_GLOB = "*LEMONAID_PLACEHOLDER*"

HOOKS = ("session-window-changed", "client-session-changed")
RETIRED_HOOKS = ("after-select-window",)  # fires alongside session-window-changed
_HOOK_INDEX = 100
_SCRATCH_SESSION = "_lma_scratch"


def size_option(position: str) -> str:
    return WIDTH_OPTION if position == "left" else HEIGHT_OPTION


def _by_position(top: str, left: str) -> str:
    return f"#{{?#{{==:#{{{POSITION_OPTION}}},top}},{top},{left}}}"


def _fitted(saved: str, client_dim: str, margin: int) -> str:
    """min(saved, client - margin), or saved when there is no client to measure.

    The client, not the window: a window the client is not showing yet still has
    the size it last had, and the hook runs before the switch resizes it.
    """
    room = f"#{{e|-|:#{{{client_dim}}},{margin}}}"
    fitted = f"#{{?#{{e|<=|:#{{{saved}}},{room}}},#{{{saved}}},{room}}}"
    return f"#{{?{client_dim},{fitted},#{{{saved}}}}}"


def _width() -> str:
    return _fitted(WIDTH_OPTION, "client_width", MIN_MAIN["left"])


def _height() -> str:
    return _fitted(HEIGHT_OPTION, "client_height", MIN_MAIN["top"])


def _split_size() -> str:
    """split-window flags: axis and size for the current position."""
    return _by_position(f"-v -b -l {_height()}", f"-h -b -l {_width()}")  # -b: top / left


def _resize_size() -> str:
    """resize-pane flags for the same size."""
    return _by_position(f"-y {_height()}", f"-x {_width()}")


def _is_the_pane() -> str:
    return f"#{{?#{{==:#{{pane_id}},#{{{PANE_OPTION}}}}},1,}}"


def _is_placeholder() -> str:
    return f"#{{m:{_PLACEHOLDER_GLOB},#{{pane_start_command}}}}"


def _pane_is_here() -> str:
    """Non-empty when the followed pane is in the hook's window."""
    return f"#{{P:{_is_the_pane()}}}"


def _pane_exists() -> str:
    """Non-empty when the followed pane is anywhere on the server."""
    return f"#{{S:#{{W:#{{P:{_is_the_pane()}}}}}}}"


def _placeholder_here() -> str:
    return f"#{{P:#{{?{_is_placeholder()},1,}}}}"


def _placeholder_id_here() -> str:
    return f"#{{P:#{{?{_is_placeholder()},#{{pane_id}},}}}}"


def _pane_is_active_here() -> str:
    return f"#{{P:#{{?#{{&&:{_is_the_pane()},#{{pane_active}}}},1,}}}}"


def _came_from(slot: str) -> str:
    """The window's last pane, unless that is `slot`; empty when there is none."""
    return f"#{{P:#{{?#{{&&:#{{pane_last}},#{{!:{slot}}}}},#{{pane_id}},}}}}"


def _focus_target_here() -> str:
    """Where focus goes when it has to leave the followed pane: the pane it came
    from, or failing that the next pane in the window."""
    came_from = _came_from(_is_the_pane())
    return f"#{{?{came_from},{came_from},#{{window_id}}.+}}"


def _unfocus_placeholders() -> str:
    """A select-pane for every window whose focused pane is a placeholder, moving
    focus to the pane it came from or else the next one. Empty when there is none."""
    came_from = _came_from(_is_placeholder())
    focused = f"#{{&&:#{{>:#{{window_panes}},1}},#{{&&:{_is_placeholder()},#{{pane_active}}}}}}"
    return f"#{{S:#{{W:#{{P:#{{?{focused},select-pane -t #{{?{came_from},{came_from},#{{window_id}}.+}} ; ,}}}}}}}}"


def hook_condition() -> str:
    """Follow is on, the pane exists, it is not here, and here is not its parking session."""
    return (
        f"#{{&&:#{{==:#{{{FOLLOW_OPTION}}},on}},"
        f"#{{&&:#{{!=:#{{session_name}},{_SCRATCH_SESSION}}},"
        f"#{{&&:{_pane_exists()},#{{!:{_pane_is_here()}}}}}}}}}"
    )


def hook_command() -> str:
    """Swap the pane into this window's placeholder, splitting one in first if
    the window has never had it.

    Focus never rides along. swap-pane -d keeps the slot active, so a switch made
    from inside the inbox would leave the placeholder focused behind it and put
    the inbox into the focused slot on the way back. If the swap focused the
    pane here, focus goes back to the pane it came from; and last of all, any
    placeholder left focused anywhere is unfocused the same way. Last because a
    select-pane moves the hook's own target to the pane it selected, and every
    format after it would be read against the wrong window.
    """
    swap = f"run-shell -C 'swap-pane -d -s #{{{PANE_OPTION}}} -t {_placeholder_id_here()}'"
    split = f"run-shell -C 'split-window -d {_split_size()} -t #{{pane_id}} {' '.join(PLACEHOLDER_COMMAND)}'"
    resize = f"run-shell -C 'resize-pane -t #{{{PANE_OPTION}}} {_resize_size()}'"
    unfocus_here = (
        f"if-shell -F '{_pane_is_active_here()}' {{\n"
        f"    run-shell -C 'select-pane -t {_focus_target_here()}'\n"
        f"  }}"
    )
    return (
        f"if-shell -F '{hook_condition()}' {{\n"
        f"  if-shell -F '{_placeholder_here()}' {{\n"
        f"    {swap}\n"
        f"  }} {{\n"
        f"    {split}\n"
        f"    {swap}\n"
        f"  }}\n"
        f"  {resize}\n"
        f"  {unfocus_here}\n"
        f"  run-shell -C '{_unfocus_placeholders()}'\n"
        f"}}"
    )


def orphan_hook_command() -> str:
    """Kill a window left holding nothing but a placeholder.

    Runs on window-pane-changed, whose context is the window whose active pane
    changed - which is what happens when a window's last real pane exits. Never
    a session's last window: with detach-on-destroy that would detach the client.
    """
    condition = (
        f"#{{&&:#{{>:#{{session_windows}},1}},"
        f"#{{&&:#{{==:#{{window_panes}},1}},{_is_placeholder()}}}}}"
    )
    return f"if-shell -F '{condition}' 'kill-window'"


def resize_hook_command() -> str:
    """Hold the slot at its saved size when the window is resized.

    tmux spreads a window resize over every pane, so a smaller font took columns
    from the sidebar instead of from the window's own panes. The slot is the
    scratch pane or a placeholder, whichever this window holds.
    """
    is_slot = f"#{{||:{_is_placeholder()},{_is_the_pane()}}}"
    slot = f"#{{P:#{{?{is_slot},#{{pane_id}},}}}}"
    return f"if-shell -F '{slot}' \"run-shell -C 'resize-pane -t {slot} {_resize_size()}'\""


def install_hooks() -> None:
    """Idempotent; one tmux round-trip. Retired hooks are removed so an older
    .tmux.conf cannot run its shell script alongside these."""
    hooks = {
        **{hook: hook_command() for hook in HOOKS},
        "window-pane-changed": orphan_hook_command(),
        "window-resized": resize_hook_command(),
    }
    argv = ["tmux"]
    for hook, command in hooks.items():
        argv += ["set-hook", "-g", f"{hook}[{_HOOK_INDEX}]", command, ";"]
    for hook in RETIRED_HOOKS:
        argv += ["set-hook", "-gu", f"{hook}[{_HOOK_INDEX}]", ";"]
    subprocess.run(argv[:-1], capture_output=True)


def publish(options: dict[str, str | None]) -> None:
    """Set global options for the hook to read; None unsets. One round-trip."""
    argv = ["tmux"]
    for name, value in options.items():
        if value is None:
            argv += ["set-option", "-gu", name, ";"]
        else:
            argv += ["set-option", "-g", name, value, ";"]
    if len(argv) > 1:
        subprocess.run(argv[:-1], capture_output=True)


def placeholders(target: str | None = None, *, whole_session: bool = False) -> list[str]:
    """Placeholder pane ids: in `target`'s window, its whole session, or the server."""
    if target is None:
        scope = ["-a"]
    elif whole_session:
        scope = ["-s", "-t", target]
    else:
        scope = ["-t", target]
    result = subprocess.run(
        ["tmux", "list-panes", *scope, "-F", "#{pane_id} #{pane_start_command}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    return [line.split()[0] for line in result.stdout.splitlines() if "LEMONAID_PLACEHOLDER" in line]


def kill_placeholders(target: str | None = None, *, whole_session: bool = False) -> None:
    for pane in placeholders(target, whole_session=whole_session):
        subprocess.run(["tmux", "kill-pane", "-t", pane], capture_output=True)


def resize_placeholders(position: str, size: str) -> None:
    """After a new size is saved, so a swap into any window lands at that size."""
    flag = "-x" if position == "left" else "-y"
    for pane in placeholders():
        subprocess.run(["tmux", "resize-pane", "-t", pane, flag, size], capture_output=True)
