import os
from pathlib import Path

from lemonaid.config import load_config
from lemonaid.grove.window import api, data


def _api(grove=None):
    calls = []
    shared = api.Shared(load_config(), grove=grove, client="/dev/ttys004")
    return api.Api(
        shared,
        hide=lambda: calls.append("hide"),
        refresh=lambda: calls.append("refresh"),
        leave=lambda: calls.append("leave"),
        stick=lambda: calls.append("stick"),
        drag=lambda: calls.append("drag"),
    ), calls


def test_before_the_first_load_the_page_gets_no_grove_and_no_drop_is_taken():
    page_api, calls = _api()

    assert page_api.data() is None
    assert page_api.refusal("1", "s", 3, 3) == "the grove is loading"
    assert page_api.block_refusal("1", [], 1, 0) == "the grove is loading"
    assert page_api.reframe("1", [], 1, 0) == "the grove is loading"
    assert page_api.plant("1", "s", 3, 3) == "the grove is loading"
    assert calls == []


def test_a_jump_tells_the_window_only_when_it_switched_the_client(monkeypatch):
    page_api, calls = _api()
    asked = []
    monkeypatch.setattr(
        data, "jump", lambda channel, client, _config: asked.append((channel, client)) or ""
    )

    assert page_api.jump("claude:1") == ""
    monkeypatch.setattr(data, "jump", lambda *_args: "No live lemon on claude:2")
    assert page_api.jump("claude:2") == "No live lemon on claude:2"
    assert asked == [("claude:1", "/dev/ttys004")]
    assert calls == ["leave"]


def test_a_drop_reloads_the_grove_only_when_it_was_saved(monkeypatch):
    page_api, calls = _api(grove=object())
    monkeypatch.setattr(
        data, "plant", lambda _grove, digit, key, x, y: "" if x == 3 else "stands there"
    )

    assert page_api.plant("1", "s", "3", 3) == ""  # the page may send numbers as strings
    assert page_api.plant("1", "s", 9, 3) == "stands there"
    assert calls == ["refresh"]


def test_a_block_move_reloads_the_grove_only_when_it_was_saved(monkeypatch):
    page_api, calls = _api(grove=object())
    monkeypatch.setattr(data, "reframe", lambda _grove, digit, sides, dx, dy: "" if dx else "no")

    assert page_api.reframe("1", ["right"], "2", 0) == ""
    assert page_api.reframe("1", [], 0, 3) == "no"
    assert calls == ["refresh"]


def test_what_the_page_keeps_comes_back_on_its_next_load():
    page_api, _calls = _api()

    assert page_api.settings() == {}
    page_api.keep({"views": {"grove": {"x": 1, "y": 2, "k": 9}}})
    assert page_api.settings() == {"views": {"grove": {"x": 1, "y": 2, "k": 9}}}


def test_the_page_is_solid_unless_the_config_lets_the_terminal_show_through():
    assert _api()[0].look()["opacity"] == 1.0

    Path(os.environ["LEMONAID_CONFIG"]).write_text("[tui]\ngrove_window_opacity = 0.6\n")
    assert _api()[0].look()["opacity"] == 0.6
    Path(os.environ["LEMONAID_CONFIG"]).write_text("[tui]\ngrove_window_opacity = 0\n")
    assert _api()[0].look()["opacity"] == 0.2  # never invisible


def test_the_lists_flip_on_the_terminal_groves_key():
    flip = {k: _api()[0].look()[k] for k in ("flipKey", "flipHold")}
    assert flip == {"flipKey": ";", "flipHold": True}

    Path(os.environ["LEMONAID_CONFIG"]).write_text(
        '[tui]\ngrove_flip_key = "!"\ngrove_flip = "toggle"\n'
    )
    flip = {k: _api()[0].look()[k] for k in ("flipKey", "flipHold")}
    assert flip == {"flipKey": "!", "flipHold": False}


def test_the_summon_key_goes_back_to_the_terminal_and_q_hides():
    page_api, calls = _api()

    page_api.to_terminal()
    page_api.dismiss()
    assert calls == ["leave", "hide"]
