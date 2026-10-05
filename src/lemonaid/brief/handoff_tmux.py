"""Inspect and replace only the recorded tmux pane for a handoff."""

import shlex
import subprocess
import time
from pathlib import Path

from ..config import BackendConfig, load_config
from ..inbox import db
from ..launch import command
from ..resume import build_resume_command
from ..tmux import submit


def _tmux(*args: str) -> str:
    result = subprocess.run(["tmux", *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def pane(session: str, index: str) -> tuple[str, str]:
    rows = _tmux(
        "list-panes", "-t", f"={session}:{index}", "-F", "#{pane_id}\t#{window_id}\t#{pane_dead}"
    ).splitlines()
    live = [line.split("\t") for line in rows if line.endswith("\t0")]
    return (live[0][0], live[0][1]) if len(live) == 1 else ("", "")


def pane_for_tty(session: str, index: str, tty: str) -> tuple[str, str]:
    rows = _tmux(
        "list-panes",
        "-t",
        f"={session}:{index}",
        "-F",
        "#{pane_id}\t#{window_id}\t#{pane_tty}\t#{pane_dead}",
    ).splitlines()
    found = [
        parts
        for line in rows
        if len(parts := line.split("\t")) == 4 and parts[2] == tty and parts[3] == "0"
    ]
    return (found[0][0], found[0][1]) if len(found) == 1 else ("", "")


def has_pane(pane_id: str, window_id: str) -> bool:
    rows = _tmux(
        "list-panes", "-t", window_id, "-F", "#{pane_id}\t#{window_id}\t#{pane_dead}"
    ).splitlines()
    return f"{pane_id}\t{window_id}\t0" in rows


def current_command(pane_id: str) -> str:
    return _tmux("display-message", "-p", "-t", pane_id, "#{pane_current_command}")


def pane_process(pane_id: str, window_id: str) -> tuple[str, bool] | None:
    """Return the pane's process id and dead flag, or None if identity changed."""
    fields = _tmux(
        "display-message",
        "-p",
        "-t",
        pane_id,
        "#{pane_id}\t#{window_id}\t#{pane_pid}\t#{pane_dead}",
    ).split("\t")
    if len(fields) != 4 or fields[:2] != [pane_id, window_id] or not fields[2]:
        return None
    return fields[2], fields[3] == "1"


def remain_on_exit(pane_id: str) -> str:
    return _tmux("show-options", "-p", "-v", "-A", "-t", pane_id, "remain-on-exit")


def set_remain_on_exit(pane_id: str, value: str) -> bool:
    return (
        subprocess.run(
            ["tmux", "set-option", "-p", "-t", pane_id, "remain-on-exit", value],
            capture_output=True,
        ).returncode
        == 0
    )


def respawn(pane_id: str, directory: Path, line: str, environment: dict[str, str]) -> str:
    """Replace the process in a pane with a command run by tmux's default shell."""
    shell = _tmux("show-options", "-gv", "default-shell") or "/bin/sh"
    args = ["tmux", "respawn-pane", "-k", "-t", pane_id, "-c", str(directory)]
    for name, value in environment.items():
        args.extend(("-e", f"{name}={value}"))
    result = subprocess.run([*args, shell, "-c", line], capture_output=True, text=True)
    return "" if result.returncode == 0 else result.stderr.strip() or "tmux respawn failed"


def resume_source(conn, row) -> bool:
    """Resume the old harness only while the recorded target still owns the pane."""
    state = pane_process(row["source_pane_id"], row["source_window_id"])
    if state is None or not row["target_pid"] or state[0] != row["target_pid"]:
        return False
    line, cwd = row["resume_line"], row["resume_cwd"]
    if not line or not cwd:
        source = db.get_by_channel(conn, row["source"], unread_only=False)
        built = (
            build_resume_command(load_config(), row["source"], source.metadata) if source else None
        )
        if built is None:
            return False
        cwd, line = built[0], shlex.join(built[1])
    if not Path(cwd).is_dir():
        return False
    prompt = (
        f"Handoff {row['token']} did not finish. Your brief remains attached. "
        "Rearm your waiters, then inspect the handoff status before retrying."
    )
    line, environment = command.harness_line(line, Path(cwd), prompt)
    return not respawn(row["source_pane_id"], Path(cwd), line, environment)


def _prompt_source_to_rearm(row, reason: str, submit_key: str) -> bool:
    if (
        not has_pane(row["source_pane_id"], row["source_window_id"])
        or current_command(row["source_pane_id"]) != row["source_command"]
    ):
        return False

    prompt = (
        f"The harness handoff {reason} before cutover. Your brief is still attached here. "
        "Rearm `lemonaid inbox watch --self` as a background task, then check "
        "`lemonaid brief handoff status " + row["token"] + "` before retrying."
    )
    if (
        subprocess.run(
            ["tmux", "send-keys", "-t", row["source_pane_id"], "-l", prompt], capture_output=True
        ).returncode
        != 0
    ):
        return False

    time.sleep(1)
    return submit.send(row["source_pane_id"], submit_key).returncode == 0


def prompt_source_to_rearm(row, reason: str) -> bool:
    try:
        backend = row["source"].partition(":")[0]
        submit_key = load_config().backends.get(backend, BackendConfig()).submit_key
        return _prompt_source_to_rearm(row, reason, submit_key)
    except OSError:
        return False
