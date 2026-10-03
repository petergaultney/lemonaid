"""The confirmation, and the two flags that skip parts of it.

`--yes` skips the prompt; `--force` overrides an inspect hook that reports work.
They are separate because an agent should be able to tear down unattended without
also being able to throw away work that hasn't been pushed.
"""

import argparse
import json

import pytest

from lemonaid.config import Config, PlaceRoot, PlacesConfig
from lemonaid.places import ownership, target, toss_cli


def _args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(
        **{"key": None, "yes": False, "force": False, "json": False, **kwargs}
    )


def _place(tmp_path, key: str, root: PlaceRoot | None = None) -> ownership.Place:
    directory = tmp_path / key
    directory.mkdir(parents=True, exist_ok=True)

    return ownership.Place(
        key, root or PlaceRoot(path=tmp_path, destroy="release {key}"), directory
    )


def _target(
    session: str, places: list[ownership.Place], partial: dict | None = None
) -> target.TossTarget:
    place = places[0] if places else None
    windows = {"@1": [_pane(session, "@1", "%1")], "@2": [_pane(session, "@2", "%2")]}

    return target.TossTarget(session, places, place, windows if session else {}, partial or {}, [])


def _pane(session: str, window: str, pane: str) -> ownership.Pane:
    return ownership.Pane(session, window, pane, None)


def _resolves_to(monkeypatch, doomed: target.TossTarget | None, why_not: str = "") -> list:
    monkeypatch.setattr(toss_cli, "load_config", lambda: Config(places=PlacesConfig()))
    monkeypatch.setattr(
        target, "resolve_toss_target", lambda config, key, unattended=False: (doomed, why_not)
    )
    monkeypatch.setattr(target, "changed_since", lambda config, key, planned, unattended=False: "")
    tossed: list = []
    monkeypatch.setattr(toss_cli.teardown, "toss", lambda *a, **kw: tossed.append((a, kw)) or None)

    return tossed


def test_confirmation_is_required_by_default(monkeypatch, tmp_path, capsys):
    doomed = _target("work", [_place(tmp_path, "feat")])
    tossed = _resolves_to(monkeypatch, doomed)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args())

    assert not tossed
    assert "Nothing was torn down" in capsys.readouterr().err


def test_confirming_tears_down(monkeypatch, tmp_path):
    doomed = _target("work", [_place(tmp_path, "feat")])
    tossed = _resolves_to(monkeypatch, doomed)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    toss_cli.cmd_toss(_args())

    assert len(tossed) == 1


def test_the_set_is_shown_before_the_prompt(monkeypatch, tmp_path, capsys):
    """The list is the decision - you look at it and know whether it's right."""
    doomed = _target("stacked", [_place(tmp_path, "base"), _place(tmp_path, "on-top")])
    _resolves_to(monkeypatch, doomed)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args())

    err = capsys.readouterr().err
    assert "place 'base'" in err
    assert "session 'stacked' closes (2 windows)" in err


def test_yes_skips_the_prompt(monkeypatch, tmp_path):
    doomed = _target("work", [_place(tmp_path, "feat")])
    tossed = _resolves_to(monkeypatch, doomed)

    def _no_input(prompt):  # pragma: no cover - reached only on a regression
        raise AssertionError("should not have prompted")

    monkeypatch.setattr("builtins.input", _no_input)

    toss_cli.cmd_toss(_args(yes=True))

    assert len(tossed) == 1


def test_json_implies_yes(monkeypatch, tmp_path):
    """There is no terminal to prompt on."""
    doomed = _target("work", [_place(tmp_path, "feat")])
    tossed = _resolves_to(monkeypatch, doomed)

    def _no_input(prompt):  # pragma: no cover - reached only on a regression
        raise AssertionError("should not have prompted")

    monkeypatch.setattr("builtins.input", _no_input)

    toss_cli.cmd_toss(_args(json=True))

    assert len(tossed) == 1


def test_json_reports_what_closed(monkeypatch, tmp_path, capsys):
    doomed = _target("work", [_place(tmp_path, "feat")])
    _resolves_to(monkeypatch, doomed)

    toss_cli.cmd_toss(_args(json=True))

    reported = json.loads(capsys.readouterr().out)
    assert reported == {
        "session": "work",
        "released": ["feat"],
        "error": None,
        "place": "feat",
        "closed_windows": ["@1", "@2"],
        "session_closed": True,
    }


def test_json_lists_windows_closed_on_their_own(monkeypatch, tmp_path, capsys):
    partial = {"@4": [_pane("katamari", "@4", "%4")], "@7": [_pane("katamari", "@7", "%7")]}
    tossed = _resolves_to(monkeypatch, _target("", [_place(tmp_path, "feat")], partial))

    toss_cli.cmd_toss(_args(json=True))

    reported = json.loads(capsys.readouterr().out)
    assert reported["session"] == ""
    assert reported["session_closed"] is False
    assert reported["closed_windows"] == ["@4", "@7"]
    assert tossed[0][0][2] == partial  # teardown gets the planned panes to check against


def test_windows_closing_in_a_surviving_session_are_shown_with_their_session(
    monkeypatch, tmp_path, capsys
):
    partial = {"@4": [_pane("katamari", "@4", "%4")], "@7": [_pane("katamari", "@7", "%7")]}
    _resolves_to(monkeypatch, _target("", [_place(tmp_path, "feat")], partial))
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "n")

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args())

    err = capsys.readouterr().err
    assert "place 'feat'" in err
    assert "2 windows in 'katamari' close (@4, @7); the session stays" in err
    assert prompts == ["close 2 windows and release the place? [y/N] "]


def test_json_for_a_place_with_no_session_closes_nothing(monkeypatch, tmp_path, capsys):
    _resolves_to(monkeypatch, _target("", [_place(tmp_path, "idle")]))

    toss_cli.cmd_toss(_args(json=True))

    reported = json.loads(capsys.readouterr().out)
    assert reported["session_closed"] is False
    assert reported["closed_windows"] == []
    assert reported["place"] == "idle"


def test_windows_left_open_elsewhere_are_shown(monkeypatch, tmp_path, capsys):
    """They end up in a released directory, which the person confirming should know."""
    place = _place(tmp_path, "feat")
    doomed = target.TossTarget("feat", [place], place, {"@1": []}, {}, ["hq:@7"])
    _resolves_to(monkeypatch, doomed)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args())

    assert "window hq:@7 stays open" in capsys.readouterr().err


def test_unfinished_work_blocks_even_with_yes(monkeypatch, tmp_path, capsys):
    """--yes means don't ask, not throw away work I haven't pushed."""
    dirty = PlaceRoot(path=tmp_path, destroy="release {key}", inspect="echo 2 unpushed")
    doomed = _target("work", [_place(tmp_path, "feat", dirty)])
    tossed = _resolves_to(monkeypatch, doomed)

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args(yes=True))

    assert not tossed
    assert "unfinished work" in capsys.readouterr().err


def test_force_overrides_unfinished_work(monkeypatch, tmp_path):
    dirty = PlaceRoot(path=tmp_path, destroy="release {key}", inspect="echo 2 unpushed")
    doomed = _target("work", [_place(tmp_path, "feat", dirty)])
    tossed = _resolves_to(monkeypatch, doomed)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    toss_cli.cmd_toss(_args(force=True))

    assert len(tossed) == 1


def test_an_unresolvable_target_exits_with_the_reason(monkeypatch, capsys):
    _resolves_to(monkeypatch, None, "Not inside tmux")

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args())

    assert "Not inside tmux" in capsys.readouterr().err


def test_a_gone_place_is_labeled_rather_than_hidden(monkeypatch, tmp_path, capsys):
    gone = ownership.Place("vanished", PlaceRoot(path=tmp_path, destroy="r {key}"), tmp_path / "x")
    _resolves_to(monkeypatch, _target("ghost", [gone]))
    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    toss_cli.cmd_toss(_args())

    assert "already gone" in capsys.readouterr().err


def test_declining_at_the_prompt_by_eof_tears_nothing_down(monkeypatch, tmp_path):
    """Ctrl-D at the prompt is a no, not a yes."""
    doomed = _target("work", [_place(tmp_path, "feat")])
    tossed = _resolves_to(monkeypatch, doomed)

    def _eof(prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args())

    assert not tossed


def test_a_plan_that_changed_during_the_prompt_tears_nothing_down(monkeypatch, tmp_path, capsys):
    """The person confirmed what they saw; if tmux no longer matches it, stop."""
    doomed = _target("work", [_place(tmp_path, "feat")])
    tossed = _resolves_to(monkeypatch, doomed)
    monkeypatch.setattr(
        target,
        "changed_since",
        lambda config, key, planned, unattended=False: "The layout changed; nothing was closed.",
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args())

    assert not tossed
    assert "The layout changed" in capsys.readouterr().err


@pytest.mark.parametrize("flags", [{"json": True}, {"yes": True}, {}])
def test_skipping_the_prompt_resolves_unattended(monkeypatch, tmp_path, flags):
    """Either flag means no one is at a prompt, which tightens a bare toss of your own session."""
    seen = {}

    def _resolve(config, key, unattended=False):
        seen["unattended"] = unattended
        return None, "refused"

    monkeypatch.setattr(toss_cli, "load_config", lambda: Config(places=PlacesConfig()))
    monkeypatch.setattr(target, "resolve_toss_target", _resolve)

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args(**flags))

    assert seen["unattended"] is bool(flags)
