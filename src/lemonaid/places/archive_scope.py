"""Codex daemon rows that cannot be assigned to their own terminal."""

from collections import abc
from pathlib import Path

from ..inbox import db


def is_unlocated_codex(row: db.Notification) -> bool:
    return (
        row.channel.startswith("codex:")
        and row.switch_source in (None, "tmux")
        and not (
            row.metadata.get("tty")
            and row.metadata.get("tmux_pane_identity")
            and row.metadata.get("tmux_session_order")
        )
    )


def closing_rows(
    rows: abc.Iterable[db.Notification], ttys: abc.Set[str], socket: str
) -> list[db.Notification]:
    return [
        row
        for row in rows
        if row.switch_source in (None, "tmux")
        and not is_unlocated_codex(row)
        and row.metadata.get("tty") in ttys
        and (row.metadata.get("tmux_socket") or socket) == socket
    ]


def doomed_rows(rows: abc.Iterable[db.Notification], directories: abc.Sequence[Path]) -> list[int]:
    return [
        row.id
        for row in rows
        if is_unlocated_codex(row)
        and (cwd := row.metadata.get("cwd"))
        and any(Path(cwd).resolve().is_relative_to(directory) for directory in directories)
    ]
