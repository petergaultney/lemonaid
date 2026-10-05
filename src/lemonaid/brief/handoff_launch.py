"""Launch the reserved harness, retrying command delivery in the same pane."""

from pathlib import Path

from ..config import load_config
from ..inbox import db
from ..launch import command, window
from . import handoff_tmux


def run(conn, row) -> None:
    config = load_config()
    windows = config.tmux_session.get_template(row["harness"])
    if not windows:
        raise ValueError(f"No tmux-session template {row['harness']!r} in config")

    line = windows[command.template_window(config.tmux_session, windows)]
    if not line.strip():
        raise ValueError(f"Tmux-session template {row['harness']!r} has no harness command")

    if error := command.unclaimable(line):
        raise ValueError(error)

    source = db.get_by_channel(conn, row["source"], unread_only=False)
    directory = Path(str(source.metadata.get("cwd"))) if source else None
    if directory is None or not directory.is_dir():
        raise ValueError("The outgoing lemon's working directory is unavailable")

    prompt = (
        f"Read {row['path']}, especially ## Handoff. Rearm ## Waiters, then run "
        f"lemonaid brief handoff accept {row['token']}. "
        f"Your brief will attach only after that acknowledgement."
    )
    typed, environment = command.harness_line(line, directory, prompt)
    if row["phase"] == "requested":
        index = handoff_tmux.target_index(row["session"])
        pane, error = window.open_window(
            row["session"],
            index,
            directory,
            {**environment, "LEMONAID_HANDOFF_TOKEN": row["token"]},
        )
        if pane is None:
            raise ValueError(error)

        conn.execute(
            """UPDATE brief_handoffs SET phase = 'prepared', target_window = ?,
               target_window_id = ?, target_pane_id = ?, target_shell = ? WHERE token = ?""",
            (
                index,
                pane.window_id,
                pane.pane_id,
                handoff_tmux.current_command(pane.pane_id),
                row["token"],
            ),
        )
        conn.commit()
    else:
        pane = window.Pane(row["target_pane_id"], row["target_window_id"])
        if handoff_tmux.pane(row["session"], row["target_window"]) != (
            pane.pane_id,
            pane.window_id,
        ):
            raise ValueError("The reserved new pane changed")

        current = handoff_tmux.current_command(pane.pane_id)
        if not current:
            raise ValueError("Cannot inspect the reserved new pane")

        if row["target"] or (row["target_shell"] and current != row["target_shell"]):
            conn.execute(
                "UPDATE brief_handoffs SET phase = 'launched' WHERE token = ?", (row["token"],)
            )
            conn.commit()
            return

    if error := window.run(pane, typed):
        raise ValueError(
            f"{error}; reserved window {row['session']}:{row['target_window'] or index}"
        )

    conn.execute("UPDATE brief_handoffs SET phase = 'launched' WHERE token = ?", (row["token"],))
    conn.commit()
