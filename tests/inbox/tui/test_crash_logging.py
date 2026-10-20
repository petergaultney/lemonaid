"""Textual's fatal handlers preserve tracebacks for both TUI entry points."""

import asyncio
import importlib.metadata

import pytest

from lemonaid.brief import target
from lemonaid.config import Config
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.briefs.brief_popup import BriefPopup


@pytest.mark.parametrize("popup", [False, True], ids=["inbox", "brief-popup"])
@pytest.mark.parametrize("worker", [False, True], ids=["callback", "worker"])
def test_fatal_error_is_logged_before_exit(tmp_path, popup, worker):
    app = BriefPopup(target.Target([], [], None, [], "Work"), Config()) if popup else LemonaidApp()

    def crash():
        try:
            raise ValueError("original cause")
        except ValueError as error:
            raise RuntimeError("brief callback failed") from error

    async def check():
        with pytest.raises(Exception, match="brief callback failed"):
            async with app.run_test() as pilot:
                if worker:
                    app.run_worker(crash, thread=True)
                else:
                    app.call_later(crash)
                await pilot.pause()
        assert app.return_code == 1

    asyncio.run(check())
    logged = (tmp_path / "state" / "logs" / "errors.log").read_text()
    assert type(app).__name__ in logged
    assert importlib.metadata.version("lemonaid-inbox") in logged
    assert "Python " in logged
    assert "Traceback (most recent call last)" in logged
    assert 'raise ValueError("original cause")' in logged
    assert "RuntimeError: brief callback failed" in logged


def test_unwritable_log_does_not_replace_the_fatal_error(monkeypatch, tmp_path):
    (tmp_path / "file").write_text("not a directory")
    failure = RuntimeError("original failure")
    app = LemonaidApp()

    def crash():
        raise failure

    async def check():
        with pytest.raises(RuntimeError) as caught:
            async with app.run_test() as pilot:
                await pilot.pause()
                monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path / "file"))
                app.call_later(crash)
                await pilot.pause()
        assert caught.value is failure
        assert app.return_code == 1

    asyncio.run(check())
