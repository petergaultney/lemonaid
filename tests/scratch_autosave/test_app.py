import asyncio

import pytest

from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.tmux import scratch
from tests.scratch_autosave.shared import start


@pytest.mark.parametrize("enabled", [False, True])
def test_tui_timer_respects_opt_in(tmux, monkeypatch, tmp_path, enabled):
    pane, _ = start(tmux, monkeypatch)
    path = tmp_path / "config.toml"
    path.write_text(f"[tmux-session]\nautosave_scratch_size = {str(enabled).lower()}\n")
    monkeypatch.setenv("LEMONAID_CONFIG", str(path))

    async def exercise():
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test() as pilot:
            await pilot.pause(0.4)
            tmux("resize-pane", "-t", pane, "-x", "70")
            await pilot.pause(1.5)
            assert scratch.saved_size("left") == ("70" if enabled else "58")

    asyncio.run(exercise())


def test_scratch_mode_outside_tmux_does_not_install_guards(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[tmux-session]\nautosave_scratch_size = true\n")
    monkeypatch.setenv("LEMONAID_CONFIG", str(path))
    monkeypatch.delenv("TMUX_PANE", raising=False)

    async def exercise():
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test():
            assert not hasattr(app, "_size_observer")

    asyncio.run(exercise())
