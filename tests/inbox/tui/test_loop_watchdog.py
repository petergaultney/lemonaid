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


def _churn(busy: bool) -> None:
    async def run() -> None:
        watchdog = loop_watchdog.Watchdog(0.1)
        watchdog.start()
        end = time.monotonic() + 1.3
        while time.monotonic() < end:
            if busy:
                _block_the_loop(0.04)  # each block is too short to log by itself
            await asyncio.sleep(0.01)
        watchdog.stop()

    asyncio.run(run())


def test_a_loop_kept_busy_by_short_blocks_is_logged(caplog, monkeypatch):
    monkeypatch.setattr(loop_watchdog, "_BUSY_WINDOW_SECONDS", 1.0)
    caplog.set_level(logging.WARNING)

    _churn(busy=True)

    (busy,) = [r.getMessage() for r in caplog.records if "loop busy" in r.getMessage()]
    assert "test_loop_watchdog._block_the_loop" in busy


def test_an_idle_loop_is_not_logged_as_busy(caplog, monkeypatch):
    monkeypatch.setattr(loop_watchdog, "_BUSY_WINDOW_SECONDS", 1.0)
    caplog.set_level(logging.WARNING)

    _churn(busy=False)

    assert "loop busy" not in caplog.text
