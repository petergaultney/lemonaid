"""`starts.start`: lemons start a few at a time, the one asked for or heard from last first,
and one that came back without restore is left alone, however close the two starts come."""

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
    found = list(starts.start(lemons, terminal, parallel, 0.05, lambda line: None, poll=0.01))
    return (
        [each for each in found if isinstance(each, run.Lemon)],
        [each for each in found if isinstance(each, report.Result)],
    )


def test_a_lemon_resumed_while_another_starts_is_left_alone():
    second = _lemon("claude:b")
    first = _lemon("claude:a")  # heard from last, so it starts first
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


def test_a_slow_lemon_holds_up_no_other():
    """With two starting at once, the third starts as soon as the second runs, while the
    first is still coming up."""
    c, b, a = _lemon("claude:c"), _lemon("claude:b"), _lemon("claude:a")
    opened: list[str] = []
    terminal = _terminal(opened)._replace(
        running=lambda lemons: {
            lemon.channel
            for lemon in lemons
            if lemon.channel != "claude:a" or "claude:c:2" in opened
        }
    )

    order = []
    for each in starts.start([a, b, c], terminal, 2, 5, lambda line: None, poll=0.01):
        order.append((each.channel, list(opened)))

    assert [channel for channel, _ in order] == ["claude:b", "claude:a", "claude:c"]
    assert order[1][1] == ["claude:a:2", "claude:b:2", "claude:c:2"]  # c began before a ran


def test_a_lemon_asked_for_starts_next_and_the_rest_most_recently_heard_from_first():
    oldest, middle, newest = _lemon("claude:a"), _lemon("claude:b"), _lemon("claude:c")
    opened: list[str] = []

    def asked() -> frozenset[str]:
        return frozenset({"claude:a"}) if opened else frozenset()

    started = list(
        starts.start(
            [oldest, middle, newest],
            _terminal(opened),
            1,
            0.05,
            lambda line: None,
            asked,
            poll=0.01,
        )
    )

    assert opened == ["claude:c:2", "claude:a:2", "claude:b:2"]
    assert [lemon.channel for lemon in started] == ["claude:c", "claude:a", "claude:b"]
