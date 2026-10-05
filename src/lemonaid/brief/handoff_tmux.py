"""Check and close only the exact tmux panes reserved for a handoff."""

import subprocess


def _tmux(*args: str) -> str:
    result = subprocess.run(["tmux", *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def pane(session: str, index: str) -> tuple[str, str]:
    rows = _tmux(
        "list-panes", "-t", f"={session}:{index}", "-F", "#{pane_id}\t#{window_id}\t#{pane_dead}"
    ).splitlines()
    live = [line.split("\t") for line in rows if line.endswith("\t0")]
    return (live[0][0], live[0][1]) if len(live) == 1 else ("", "")


def target_index(session: str) -> str:
    lines = _tmux("list-windows", "-t", f"={session}", "-F", "#{window_index}").splitlines()
    return str(max((int(line) for line in lines if line.isdigit()), default=0) + 1)


def current_command(pane_id: str) -> str:
    return _tmux("display-message", "-p", "-t", pane_id, "#{pane_current_command}")


def close_old(row) -> bool:
    windows = subprocess.run(
        ["tmux", "list-windows", "-a", "-F", "#{window_id}"], capture_output=True, text=True
    )
    if windows.returncode != 0:
        return False

    if row["source_window_id"] not in windows.stdout.splitlines():
        return True

    panes = subprocess.run(
        [
            "tmux",
            "list-panes",
            "-t",
            row["source_window_id"],
            "-F",
            "#{pane_id}\t#{pane_current_command}\t#{pane_dead}",
        ],
        capture_output=True,
        text=True,
    )
    lines = panes.stdout.splitlines()
    if panes.returncode != 0 or len(lines) != 1:
        return False

    parts = lines[0].split("\t", 2)
    if len(parts) != 3:
        return False

    pane_id, command, dead = parts
    if pane_id != row["source_pane_id"] or (dead != "1" and command != row["source_command"]):
        return False

    return (
        subprocess.run(
            ["tmux", "kill-window", "-t", row["source_window_id"]], capture_output=True
        ).returncode
        == 0
    )
