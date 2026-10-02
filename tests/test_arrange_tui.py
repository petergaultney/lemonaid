"""`[inbox] arrange` orders and folds lma's list, and lma falls back to its own order without it."""

import asyncio
import os
import shlex
import sys
import time
from pathlib import Path

import pytest
from textual.widgets import Static

from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp

_REVERSE = """
from lemonaid.inbox.arrange import answer

def arrange(snapshot):
    rows = answer.default(snapshot)["rows"]
    return {"rows": rows[:-1][::-1], "folded": rows[-1:], "fold_label": "quiet"}
"""


@pytest.fixture(autouse=True)
def _keep_sessions(monkeypatch):
    """The test tmux has none of these ttys, so the watcher would archive every row."""
    monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)


def _sessions(*names: str) -> list[int]:
    """Read sessions, newest last, so the inbox's own order is *names* reversed."""
    ids = []
    with db.connect() as conn:
        for i, name in enumerate(names):
            n = db.add(conn, f"claude:{name}", "m", name, {"tty": f"/dev/ttys-{name}"})
            conn.execute(
                "UPDATE notifications SET switch_source = 'tmux', status = 'read',"
                " created_at = ? WHERE id = ?",
                (time.time() - 100 + i, n.id),
            )
            ids.append(n.id)
        conn.commit()
    return ids


def _serve(tmp_path: Path, code: str) -> str:
    script = tmp_path / "arranger.py"
    script.write_text(code)
    return shlex.join([sys.executable, "-m", "lemonaid", "inbox", "arrange", "serve", str(script)])


def _configure(arrange: str) -> None:
    Path(os.environ["LEMONAID_CONFIG"]).write_text(f"[inbox]\narrange = {arrange!r}\n")


def _drawn() -> tuple[list[int], str, str]:
    """The rows lma draws, its fold line, and its status line, once the arranger answers."""

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 40)) as pilot:
            for _ in range(100):
                await pilot.pause(0.05)
                status = str(app.query_one("#status", Static).render())
                if app._fold_name or "arrange:" in status:
                    break
            return (
                [n.id for n in app._drawn],
                str(app.query_one("#fold_label", Static).render()),
                status,
            )

    return asyncio.run(run())


def test_the_arranger_orders_and_folds_the_list(tmp_path):
    _, b, c = _sessions("a", "b", "c")
    _configure(_serve(tmp_path, _REVERSE))

    drawn, fold_line, _ = _drawn()

    assert drawn == [b, c]  # the inbox's own order is c, b, a
    assert fold_line.startswith("▸ quiet (1)")


def test_a_failing_arranger_falls_back_and_says_why(tmp_path):
    a, b, c = _sessions("a", "b", "c")
    _configure(_serve(tmp_path, "def arrange(snapshot):\n    return snapshot['nope']\n"))

    drawn, _, status = _drawn()

    assert drawn == [c, b, a]
    assert "arrange: arranger says: KeyError: 'nope'" in status
