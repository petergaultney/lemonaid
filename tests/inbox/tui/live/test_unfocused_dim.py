import asyncio
import os
import threading
from pathlib import Path

from rich.color import Color as RichColor
from rich.segment import Segment
from rich.style import Style
from textual.color import Color

from lemonaid import config
from lemonaid.inbox.tui import unfocused_dim
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.watchers import focus


def test_the_filter_adds_dim_and_keeps_colors():
    style = Style(color="red", bgcolor="default")
    [out] = unfocused_dim.Dim().apply([Segment("x", style)], Color(0, 0, 0))
    assert out.style.dim and out.style.color == style.color and out.style.bgcolor == style.bgcolor


def test_a_percentage_blends_colors_toward_the_background_and_keeps_backgrounds():
    style = Style(color=RichColor.from_rgb(200, 100, 0), bgcolor=RichColor.default())
    [out] = unfocused_dim.Dim(0.5).apply([Segment("x", style)], Color(0, 0, 0))
    assert out.style.color.triplet == (100, 50, 0)
    assert out.style.bgcolor.is_default and not out.style.dim


def test_a_percentage_fades_palette_colors_and_leaves_the_default_color_alone():
    palette, default = Style(color="red"), Style(color="default")
    out = unfocused_dim.Dim(0.5).apply(
        [Segment("a", palette), Segment("b", default)], Color(0, 0, 0)
    )
    assert out[0].style.color.triplet is not None and out[0].style.color != palette.color
    assert out[1].style.color == default.color


def test_unfocused_dim_defaults_off_and_rejects_unknown_values(capsys):
    assert config.TuiConfig().unfocused_dim == "off"
    assert config._unfocused_dim("dim") == "dim"
    assert config._unfocused_dim(35) == "35"
    assert config._unfocused_dim("12.5") == "12.5"
    for bad in ("loud", 0, 100, True):
        assert config._unfocused_dim(bad) == "off"
    assert "unfocused_dim" in capsys.readouterr().err


def _dimmed_while(monkeypatch, setting: str, receives: bool, scratch: bool = True) -> bool:
    Path(os.environ["LEMONAID_CONFIG"]).write_text(f'[tui]\nunfocused_dim = "{setting}"\n')
    monkeypatch.setenv("TMUX_PANE", "%9")
    monkeypatch.setattr(focus, "pane_receives_keys", lambda pane: receives)

    async def check() -> bool:
        app = LemonaidApp(scratch_mode=scratch)
        async with app.run_test(size=(50, 20)) as pilot:
            await pilot.pause()
            return app._dim.enabled

    return asyncio.run(check())


def test_dims_only_when_configured_and_the_pane_is_unselected(monkeypatch):
    assert _dimmed_while(monkeypatch, "dim", receives=False)
    assert not _dimmed_while(monkeypatch, "dim", receives=True)
    assert not _dimmed_while(monkeypatch, "off", receives=False)


def test_never_dims_outside_the_scratch_pane(monkeypatch):
    assert not _dimmed_while(monkeypatch, "dim", receives=False, scratch=False)


def test_a_pane_switch_undims_without_waiting_for_a_refresh(monkeypatch):
    Path(os.environ["LEMONAID_CONFIG"]).write_text('[tui]\nunfocused_dim = "dim"\n')
    monkeypatch.setenv("TMUX_PANE", "%9")
    receives = False
    monkeypatch.setattr(focus, "pane_receives_keys", lambda pane: receives)

    async def check():
        nonlocal receives
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 20)) as pilot:
            await pilot.pause()
            assert app._dim.enabled
            receives = True
            app.on_app_focus()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert not app._dim.enabled

    asyncio.run(check())


def test_a_superseded_probe_finishing_last_does_not_overwrite_the_newer_answer(monkeypatch):
    Path(os.environ["LEMONAID_CONFIG"]).write_text('[tui]\nunfocused_dim = "dim"\n')
    monkeypatch.setenv("TMUX_PANE", "%9")
    first_started, release_first = threading.Event(), threading.Event()
    calls = []

    def probe(pane):
        calls.append(pane)
        if len(calls) == 1:
            first_started.set()
            release_first.wait(5)
            return False

        return True

    monkeypatch.setattr(focus, "pane_receives_keys", lambda pane: True)

    async def until(condition):
        for _ in range(100):
            if condition():
                return
            await asyncio.sleep(0.02)
        raise AssertionError("timed out")

    async def check():
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 20)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(focus, "pane_receives_keys", probe)
            app._recheck_pane_focus()  # blur: held until released, then answers False
            await until(first_started.is_set)
            app._recheck_pane_focus()  # focus: answers True at once
            await until(lambda: len(calls) == 2)
            await until(lambda: app.has_class("-input-active"))
            release_first.set()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert not app._dim.enabled
            assert app.has_class("-input-active")

    asyncio.run(check())
