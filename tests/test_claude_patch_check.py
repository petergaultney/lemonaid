"""The inbox checks the Claude binary's patch status in a child process.

Textual swaps `sys.stderr` for a capture object with no file descriptor while
the app runs, so the check must not depend on the parent's stderr fd.
"""

import asyncio
from multiprocessing import resource_tracker

from lemonaid.inbox.tui import app as tui_app


def _mounted_status(monkeypatch, binary) -> str | None:
    """The status the mounted app settles on; fails if the check names a semaphore."""
    registered: list[tuple[str, str]] = []
    monkeypatch.setattr(tui_app, "find_binary", lambda: binary)
    monkeypatch.setattr(resource_tracker, "register", lambda *a: registered.append(a))

    async def run():
        app = tui_app.LemonaidApp()
        async with app.run_test(size=(80, 20)) as pilot:
            for _ in range(200):
                if app._claude_patch_status is not None:
                    break

                await asyncio.sleep(0.05)
            await pilot.pause()
            return app._claude_patch_status

    status = asyncio.run(run())
    assert registered == []
    return status


def test_an_unpatched_binary_reports_unpatched_inside_the_tui(monkeypatch, tmp_path):
    binary = tmp_path / "2.1.300"
    binary.write_bytes(b"x=600000,a=30000,b=6000;")

    assert _mounted_status(monkeypatch, binary) == "unpatched"


def test_a_patched_binary_reports_patched_inside_the_tui(monkeypatch, tmp_path):
    binary = tmp_path / "2.1.300"
    binary.write_bytes(b"x=600000,a=30000,b= 500;")

    assert _mounted_status(monkeypatch, binary) == "patched"


def test_an_unreadable_binary_reports_unknown(monkeypatch, tmp_path):
    assert _mounted_status(monkeypatch, tmp_path / "2.1.300") == "unknown"
