import asyncio
import logging

from textual.app import App

from lemonaid.inbox.tui import input_watchdog


class _App(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.watchdog = input_watchdog.Watchdog(self, 0.3)
        self.release = asyncio.Event()

    def on_mount(self) -> None:
        self.watchdog.start()

    async def wedged_handler(self) -> None:
        await self.release.wait()

    async def batching_timer(self) -> None:
        with self.batch_update():
            await self.release.wait()


def _messages(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name.endswith("tui.input")]


def _run(caplog, start: str = "") -> tuple[list[str], list[str]]:
    """What was logged while *start* held things up, and what after it let go."""

    async def run() -> tuple[list[str], list[str]]:
        app = _App()
        async with app.run_test():
            if start == "handler":
                app.call_later(app.wedged_handler)
            elif start == "timer":
                app.set_interval(0.01, app.batching_timer)
            await asyncio.sleep(1.5)
            during = _messages(caplog)
            app.release.set()
            await asyncio.sleep(0.8)
            app.watchdog.stop()
            return during, _messages(caplog)[len(during) :]

    return asyncio.run(run())


def test_a_handler_that_never_returns_is_logged_with_what_it_awaits(caplog):
    caplog.set_level(logging.WARNING)

    (stuck,), after = _run(caplog, "handler")

    assert stuck.startswith("_App(")
    assert "has not handled a message" in stuck
    assert "_App.wedged_handler" in stuck
    (recovered,) = after
    assert recovered.startswith("_App(") and "answered again" in recovered


def test_an_interval_callback_holding_a_batch_is_logged(caplog):
    caplog.set_level(logging.WARNING)

    during, _after = _run(caplog, "timer")

    assert any("_App.batching_timer" in line for line in during)
    assert any("batches open: 1" in line for line in during)


def test_a_responsive_app_logs_nothing(caplog):
    caplog.set_level(logging.WARNING)

    assert _run(caplog) == ([], [])
