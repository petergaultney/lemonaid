"""End a lemon on a test-owned tmux server: its harness stops, and only its own pane closes."""

from pathlib import Path

from lemonaid.config import Config
from lemonaid.inbox import db, ended
from lemonaid.launch.end import coordinator, plan
from lemonaid.launch.restart import native, pane, process, state

from ..restart import runtime_fixture
from . import shared

runtime = runtime_fixture.runtime
_CHANNEL = runtime_fixture.shared.CHANNEL


def _plan(path: Path, lemon_id: str) -> dict:
    path.write_text(path.read_text().replace("# Restart\n", "# Restart\n\nStatus: done\n", 1))
    with db.connect() as conn:
        return plan.build(conn, lemon_id, Config())


def _end(path: Path, lemon_id: str) -> list[str]:
    planned = _plan(path, lemon_id)
    done = coordinator.run(planned)
    assert not process.same(process.Identity(**planned["source"]))
    assert state.latest(_CHANNEL)["phase"] == "ended"
    return done


def _cause() -> str:
    with db.connect() as conn:
        row = db.get_by_channel(conn, _CHANNEL, unread_only=False)
    return ended.cause(row.metadata)


def _windows(socket: str) -> list[str]:
    return pane.run(socket, "list-windows", "-t", "=test", "-F", "#{window_panes}").split()


def test_its_window_closes_and_the_rest_of_its_session_stays(runtime):
    path, lemon_id, target = runtime
    pane.run(target.socket, "new-window", "-d", "-t", "=test:", "sleep 600")

    done = _end(path, lemon_id)

    assert done[0].startswith("stopped its harness, pid ")
    assert done[-1] == f"closed its pane {target.pane} and its window {target.window}"
    assert _windows(target.socket) == ["1"]
    assert _cause() == ended.ENDED


def test_a_pane_beside_it_keeps_its_window_open(runtime):
    path, lemon_id, target = runtime
    pane.run(target.socket, "split-window", "-d", "-t", target.pane, "sleep 600")

    done = _end(path, lemon_id)

    assert done[-1] == f"closed its pane {target.pane}, leaving the other panes in its window"
    assert _windows(target.socket) == ["1"]


def test_the_last_pane_of_its_session_stays_open(runtime):
    path, lemon_id, target = runtime

    done = _end(path, lemon_id)

    assert done[-1] == (
        f"left its pane {target.pane} open: it is the last pane of session 'test';"
        " `lemonaid place toss` ends a place"
    )
    assert pane.by_id(target.socket, target.pane).dead


def test_a_live_harness_is_stopped_though_its_card_was_archived(runtime):
    path, lemon_id, target = runtime
    shared.archive_card(_CHANNEL)
    pane.run(target.socket, "new-window", "-d", "-t", "=test:", "sleep 600")

    done = _end(path, lemon_id)

    assert done[0].startswith("stopped its harness, pid ")
    assert done[-1] == f"closed its pane {target.pane} and its window {target.window}"
    assert _cause() == ended.ARCHIVED


def test_an_interrupted_end_asks_for_inspection_before_a_resume(runtime):
    path, lemon_id, _ = runtime
    token = state.reserve(_plan(path, lemon_id))
    state.update(token, "partial", error="interrupted after SIGTERM")

    assert native.recovery_required(_CHANNEL)
    assert f"lemonaid lemon end --status {token}" in state.inspection(_CHANNEL)
