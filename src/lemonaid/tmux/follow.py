"""The follow hook: what moves the scratch pane into the window you switched to.

It runs inside the tmux server, as `if-shell -F` and `run-shell -C`, with no
shell process. That is what makes it correct rather than merely fast. One
switch fires two hooks (the session's window changed, and the client's session
changed), and hooks run one after another in the server - so the second sees
the pane the first joined and does nothing. Two background shells each saw the
pane absent and both joined it, and a pane joined twice into one window comes
out at whatever width the second split left it.

Everything the hook reads is a tmux option, which the server expands without
leaving the process. The files in the state directory remain the record that
survives a server restart; scratch.py writes both.
"""

import subprocess

MAX_SHARE = 0.4  # most of a window the scratch pane may take

FOLLOW_OPTION = "@lemonaid_follow"  # "on" or "off"
PANE_OPTION = "@lemonaid_scratch_pane"  # the pane to follow with; unset while parked
POSITION_OPTION = "@lemonaid_scratch_position"  # "left" or "top"
WIDTH_OPTION = "@lemonaid_scratch_width"  # columns, for a left pane
HEIGHT_OPTION = "@lemonaid_scratch_height"  # rows, for a top pane
MARKER_OPTION = "@lemonaid_scratch"  # set on the pane itself; how it is found again

HOOKS = ("session-window-changed", "client-session-changed")
RETIRED_HOOKS = ("after-select-window",)  # fires alongside session-window-changed
_HOOK_INDEX = 100
_SCRATCH_SESSION = "_lma_scratch"


def size_option(position: str) -> str:
    return WIDTH_OPTION if position == "left" else HEIGHT_OPTION


def _capped(saved: str, client_dim: str, window_dim: str) -> str:
    """min(saved, MAX_SHARE of the client), as a tmux format.

    The client rather than the window: a window no client has displayed yet is
    tmux's default-size of 80x24 until the switch resizes it, and the hook runs
    first. The window is the fallback for a hook with no client in its context.
    """
    dim = f"#{{?{client_dim},#{{{client_dim}}},#{{{window_dim}}}}}"
    cap = f"#{{e|/|:#{{e|*|:{dim},{int(MAX_SHARE * 100)}}},100}}"
    return f"#{{?#{{e|<=|:#{{{saved}}},{cap}}},#{{{saved}}},{cap}}}"


def _axis_and_size() -> str:
    width = _capped(WIDTH_OPTION, "client_width", "window_width")
    height = _capped(HEIGHT_OPTION, "client_height", "window_height")
    return f"#{{?#{{==:#{{{POSITION_OPTION}}},top}},-v -l {height},-h -l {width}}}"


def _is_the_pane() -> str:
    return f"#{{?#{{==:#{{pane_id}},#{{{PANE_OPTION}}}}},1,}}"


def _pane_is_here() -> str:
    """Non-empty when the followed pane is in the hook's window."""
    return f"#{{P:{_is_the_pane()}}}"


def _pane_exists() -> str:
    """Non-empty when the followed pane is anywhere on the server."""
    return f"#{{S:#{{W:#{{P:{_is_the_pane()}}}}}}}"


def hook_condition() -> str:
    """Follow is on, the pane exists, it is not here, and here is not its parking session."""
    return (
        f"#{{&&:#{{==:#{{{FOLLOW_OPTION}}},on}},"
        f"#{{&&:#{{!=:#{{session_name}},{_SCRATCH_SESSION}}},"
        f"#{{&&:{_pane_exists()},#{{!:{_pane_is_here()}}}}}}}}}"
    )


def hook_command() -> str:
    """The whole hook. -d keeps focus where the switch put it, so nothing is selected back."""
    join = f"join-pane -d -b {_axis_and_size()} -s #{{{PANE_OPTION}}}"
    return f"if-shell -F '{hook_condition()}' \"run-shell -C '{join}'\""


def install_hooks() -> None:
    """Idempotent; one tmux round-trip. Retired hooks are removed so an older
    .tmux.conf cannot run its shell script alongside these."""
    command = hook_command()
    argv = ["tmux"]
    for hook in HOOKS:
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
