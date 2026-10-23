import asyncio
import logging
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
