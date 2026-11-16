"""`starts.start` leaves alone a lemon that came back without restore, however close the two
starts come."""

import threading
import time

from lemonaid.inbox import db
from lemonaid.messages import resume_log, start_lock, store
from lemonaid.restore import launch, report, run, starts
from lemonaid.tmux import restore as tmux_restore

_LEMON_ID = "lost-task.LostOne"


def _lemon(channel: str, lemon_id: str = "") -> run.Lemon:
    with db.connect() as conn:
        db.add(conn, channel, "waiting", metadata={"tty": "/dev/ttys901"}, switch_source="tmux")
        db.mark_lost(conn, channel, "test", "")
        row = db.get_by_channel(conn, channel, unread_only=False)
    assert row is not None
    return run.Lemon(
        row,
        run.Spot(f"{channel}:2", "", None),
        launch.Launch("/tmp", "resume", {}, False),
        lemon_id,
        "",
        "",
    )


def _terminal(opened: list[str], on_open=lambda spot: None) -> run.Terminal:
    def open_window(spot, cwd, environment):
        opened.append(spot.where)
        on_open(spot)
        return f"@{len(opened)}", ""

    return tmux_restore.terminal(True)._replace(
        open=open_window,
        type=lambda window, line: "",
        close=lambda window: None,
        running=lambda lemons: {lemon.channel for lemon in lemons},
        found=lambda rows, dry_run: set(),
        seen=lambda where: report.Seen(False, ""),
    )


def _start(lemons, terminal, parallel=2):
    return starts.start(lemons, terminal, parallel, 0.05, lambda line: None, poll=0.01)


def test_a_lemon_resumed_while_an_earlier_one_in_its_batch_starts_is_left_alone():
    first, second = _lemon("claude:a"), _lemon("claude:b")
    opened: list[str] = []

    def resume_b(spot) -> None:
        with db.connect() as conn:
            db.add(
                conn, "claude:b", "resumed", metadata={"tty": "/dev/ttys990"}, switch_source="tmux"
            )

    started, results = _start([first, second], _terminal(opened, resume_b))

    assert opened == ["claude:a:2"]
    assert [lemon.channel for lemon in started] == ["claude:a"]
    assert [(r.channel, r.outcome) for r in results] == [("claude:b", report.RUNNING)]


def test_a_resume_already_launching_holds_restore_off_until_it_is_recorded():
    """A `lemon resume` that passed its checks before restore began still holds the start
    lock while it launches; restore waits for it, then finds the start in the start log."""
    lemon = _lemon("claude:a", _LEMON_ID)
    opened: list[str] = []
    launching = threading.Event()

    def resume() -> None:
        with start_lock.held("claude:a"):
            launching.set()
            time.sleep(0.2)
            resume_log.record(store.mailbox_for_id(_LEMON_ID))

    resumer = threading.Thread(target=resume)
    resumer.start()
    launching.wait()
    started, results = _start([lemon], _terminal(opened))
    resumer.join()

    assert opened == []
    assert started == []
    assert [r.outcome for r in results] == [report.RUNNING]
