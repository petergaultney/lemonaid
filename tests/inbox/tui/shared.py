"""Helpers for driving the inbox app with several lemons, each with its own brief."""

import dataclasses
import threading
from pathlib import Path

from lemonaid.brief import sidebar, target
from lemonaid.inbox import db
from lemonaid.inbox.tui.watchers import watcher_hooks


def lemons(monkeypatch, tmp_path: Path, count: int) -> tuple[list[db.Notification], dict]:
    """Rows in list order, each with its own brief, and the sidebar state they share."""
    with db.connect() as conn:
        rows = [
            db.add(
                conn,
                f"claude:lemon-{index}",
                "working",
                f"lemon-{index}",
                {"cwd": str(tmp_path), "tty": f"/dev/test-{index}"},
                switch_source="tmux",
                status="read",
                created_at=1000.0 - index,
            )
            for index in range(count)
        ]
    targets = {}
    for index, row in enumerate(rows):
        place = tmp_path / f"lemon-{index}"
        place.mkdir()
        path = place / "task.md"
        path.write_text(f"# Lemon {index}\n\nStatus: working\n\n## Now\n- Step {index}.\n")
        targets[row.channel] = target.Target([path], [place], place, ["work"], f"Lemon {index}")

    state: dict = {"shown": None, "switched": [], "cleared": 0, "result": True}
    state["gate"] = threading.Event()
    state["gate"].set()

    def switch_beside(metadata, switch_source, config, found):
        state["switched"].append(metadata["channel"])
        state["gate"].wait(5)
        if state["result"]:
            state["shown"] = found
        return state["result"]

    def clear(pane):
        state["cleared"] += 1
        state["shown"] = None

    def toggle(found, window):
        state["shown"] = found
        return True

    def show(found, window):
        state["shown"] = found
        return True

    monkeypatch.setenv("TMUX_PANE", "%9")
    # The watcher reports detached channels on its own poll, which would race the
    # ones a test sets by hand.
    monkeypatch.setattr(watcher_hooks, "start", lambda *args: None)
    monkeypatch.setattr("lemonaid.inbox.tui.app.is_follow_enabled", lambda: True)
    monkeypatch.setattr("lemonaid.inbox.tui.app.current_position", lambda _: "left")
    monkeypatch.setattr("lemonaid.inbox.tui.app.brief.attached.for_rows", lambda *args: {})
    real_for_notification = target.for_notification
    monkeypatch.setattr(
        target,
        "for_notification",
        lambda row, *args: dataclasses.replace(
            targets[row.channel], lemon=real_for_notification(row, {}).lemon
        ),
    )
    monkeypatch.setattr(sidebar, "window_id", lambda _: "@target")
    monkeypatch.setattr(sidebar, "toggle", toggle)
    monkeypatch.setattr(sidebar, "clear", clear)
    monkeypatch.setattr(sidebar, "switch_beside", switch_beside)
    monkeypatch.setattr(sidebar, "show", show)
    monkeypatch.setattr(
        sidebar, "read", lambda pane: (state["shown"], "@target") if state["shown"] else None
    )
    state["targets"] = [target.for_notification(row, {}) for row in rows]
    return rows, state


async def until(pilot, condition) -> None:
    for _ in range(200):
        if condition():
            return
        await pilot.pause(0.01)
    raise AssertionError("condition never held")
