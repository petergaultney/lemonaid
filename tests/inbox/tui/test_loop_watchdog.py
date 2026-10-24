import asyncio
import logging
import sys
import time

from lemonaid.inbox.tui import loop_watchdog


def _block_the_loop(seconds: float) -> None:
    time.sleep(seconds)


def _watch(block_seconds: float) -> float:
    async def run() -> float:
        watchdog = loop_watchdog.Watchdog(0.1)
        watchdog.start()
        await asyncio.sleep(0.1)
        if block_seconds:
            _block_the_loop(block_seconds)
        await asyncio.sleep(0.2)
        watchdog.stop()
        return watchdog.worst(time.monotonic())

    return asyncio.run(run())


def test_a_blocked_loop_is_logged_with_where_it_was(caplog):
    caplog.set_level(logging.WARNING)

    worst = _watch(0.4)

    assert 0.3 < worst < 0.45
    (record,) = [r for r in caplog.records if r.name.endswith("tui.loop")]
    assert "loop blocked" in record.getMessage()
    assert record.getMessage().endswith("test_loop_watchdog._block_the_loop")


def test_a_healthy_loop_logs_nothing(caplog):
    caplog.set_level(logging.WARNING)

    assert _watch(0.0) == 0.0
    assert not [r for r in caplog.records if r.name.endswith("tui.loop")]


def test_a_stall_the_thread_never_sampled_is_still_recorded(caplog):
    caplog.set_level(logging.WARNING)

    async def run() -> float:
        watchdog = loop_watchdog.Watchdog(0.1)
        watchdog._beat = time.monotonic() - 0.17
        watchdog._stamp(asyncio.get_running_loop())
        watchdog.stop()
        return watchdog.worst(time.monotonic())

    assert 0.11 < asyncio.run(run()) < 0.2
    assert "an unsampled call" in caplog.text


def test_a_long_block_is_logged_with_its_stack_before_it_ends(caplog):
    caplog.set_level(logging.WARNING)

    _watch(1.3)

    (during,) = [r.getMessage() for r in caplog.records if "so far" in r.getMessage()]
    assert "in _block_the_loop" in during


def _idle_for_a_while() -> None:
    async def run() -> None:
        watchdog = loop_watchdog.Watchdog(0.1)
        watchdog.start()
        await asyncio.sleep(1.3)
        watchdog.stop()

    asyncio.run(run())


def _selector_frame():
    """A frame from a module named `selectors`, where an idle loop waits."""
    scope = {"__name__": "selectors", "sys": sys}
    exec("def select():\n    return sys._getframe()\n", scope)
    return scope["select"]()


def test_a_loop_kept_busy_by_short_blocks_is_logged(caplog):
    caplog.set_level(logging.WARNING)
    watchdog = loop_watchdog.Watchdog(0.1)
    busy = sys._getframe()  # anywhere but the selector counts as busy
    for _ in range(7):
        watchdog._sample_busy(busy)
    for _ in range(2):
        watchdog._sample_busy(_selector_frame())
    watchdog._window -= loop_watchdog._BUSY_WINDOW_SECONDS

    watchdog._sample_busy(busy)

    (logged,) = [r.getMessage() for r in caplog.records if "loop busy" in r.getMessage()]
    assert logged.startswith("loop busy 80% over")
    assert "test_a_loop_kept_busy_by_short_blocks_is_logged" in logged


def test_an_idle_loop_is_not_logged_as_busy(caplog, monkeypatch):
    monkeypatch.setattr(loop_watchdog, "_BUSY_WINDOW_SECONDS", 1.0)
    caplog.set_level(logging.WARNING)

    _idle_for_a_while()

    assert "loop busy" not in caplog.text
