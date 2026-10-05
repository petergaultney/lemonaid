"""Replace the outgoing harness in its original pane after readiness."""

import shlex
from pathlib import Path

from ..config import load_config
from ..inbox import db
from ..launch import command
from ..resume import build_resume_command
from . import handoff_tmux


def reserve_source(conn, row) -> None:
    """Keep the recorded pane available before asking its harness to exit."""
    if not row["source_pane_id"] or row["source_pid"]:
        return
    pane_id = row["source_pane_id"]
    state = handoff_tmux.pane_process(pane_id, row["source_window_id"])
    if state is None or state[1] or handoff_tmux.current_command(pane_id) != row["source_command"]:
        raise ValueError("The outgoing pane changed before the exit request")
    previous = handoff_tmux.remain_on_exit(pane_id)
    if previous not in ("on", "off", "failed"):
        raise ValueError("Could not inspect the outgoing pane's exit behavior")
    if not handoff_tmux.set_remain_on_exit(pane_id, "on"):
        raise ValueError("Could not preserve the pane for recovery")
    conn.execute(
        "UPDATE brief_handoffs SET source_pid = ?, remain_on_exit = ? WHERE token = ?",
        (state[0], previous, row["token"]),
    )
    conn.commit()


def configured_line(harness: str, fallback: str = "") -> str:
    config = load_config()
    windows = config.tmux_session.get_template(harness)
    if not windows:
        if fallback:
            return fallback

        raise ValueError(f"No tmux-session template {harness!r} in config")

    line = windows[command.template_window(config.tmux_session, windows)]
    if not line.strip():
        raise ValueError(f"Tmux-session template {harness!r} has no harness command")

    return line


def run(conn, row) -> bool:
    line = configured_line(row["harness"])

    if error := command.unclaimable(line):
        raise ValueError(error)

    source = db.get_by_channel(conn, row["source"], unread_only=False)
    directory = Path(str(source.metadata.get("cwd"))) if source else None
    if directory is None or not directory.is_dir():
        raise ValueError("The outgoing lemon's working directory is unavailable")
    if not source or not (
        resume := build_resume_command(load_config(), row["source"], source.metadata)
    ):
        raise ValueError("The outgoing session has no usable resume command")
    if not resume[1] or not Path(resume[0]).is_dir():
        raise ValueError("The outgoing session cannot be resumed from its recorded directory")
    # Validate the configured command before replacing the only running harness.
    shlex.split(line)

    prompt = (
        f"Read {row['path']}, especially ## Handoff. Rearm ## Waiters, then run "
        f"lemonaid brief handoff accept {row['token']}. "
        f"Your brief will attach only after that acknowledgement."
    )
    typed, environment = command.harness_line(line, directory, prompt)
    pane_id = row["source_pane_id"]
    window_id = row["source_window_id"]
    if row["phase"] == "requested":
        state = handoff_tmux.pane_process(pane_id, window_id)
        if (
            state is None
            or (row["source_pid"] and state[0] != row["source_pid"])
            or (
                not state[1]
                and handoff_tmux.current_command(pane_id) != row["source_command"]
                and not handoff_tmux.returned_to_shell(pane_id, state[0], row["source_command"])
            )
        ):
            raise ValueError("The outgoing pane changed before launch")
        if row["source_pid"]:
            previous = row["remain_on_exit"]
        else:
            previous = handoff_tmux.remain_on_exit(pane_id)
            if previous not in ("on", "off", "failed"):
                raise ValueError("Could not inspect the outgoing pane's exit behavior")
            if not handoff_tmux.set_remain_on_exit(pane_id, "on"):
                raise ValueError("Could not preserve the pane for recovery")

        conn.execute(
            """UPDATE brief_handoffs SET phase = 'prepared', target_window = ?,
               target_window_id = ?, target_pane_id = ?, source_pid = ?,
               remain_on_exit = ?, resume_line = ?, resume_cwd = ? WHERE token = ?""",
            (
                row["source_window"],
                window_id,
                pane_id,
                state[0],
                previous,
                shlex.join(resume[1]),
                resume[0],
                row["token"],
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM brief_handoffs WHERE token = ?", (row["token"],)
        ).fetchone()

    state = handoff_tmux.pane_process(pane_id, window_id)
    if state is None:
        raise ValueError("The reserved pane changed before launch")
    if state[0] != row["source_pid"]:
        # The prior respawn may have succeeded just before the coordinator died.
        # The tokened accept can still finish, but we cannot safely roll it back.
        raise ValueError("Pane process changed during launch; inspect before retrying")
    if not state[1] and not handoff_tmux.returned_to_shell(
        pane_id, row["source_pid"], row["source_command"]
    ):
        if handoff_tmux.current_command(pane_id) != row["source_command"]:
            raise ValueError("The outgoing pane changed before launch")
        return False

    if error := handoff_tmux.respawn(
        pane_id,
        directory,
        typed,
        {**environment, "LEMONAID_HANDOFF_TOKEN": row["token"]},
        kill=not state[1],
    ):
        raise ValueError(f"Could not launch the new harness: {error}")
    target = handoff_tmux.pane_process(pane_id, window_id)
    if target is None or target[0] == row["source_pid"]:
        raise ValueError("Could not verify the replacement pane process")
    conn.execute(
        "UPDATE brief_handoffs SET phase = 'launched', target_pid = ? WHERE token = ?",
        (target[0], row["token"]),
    )
    conn.commit()
    return True
