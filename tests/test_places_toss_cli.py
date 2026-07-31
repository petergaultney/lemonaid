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


def _resolves_to(monkeypatch, doomed: target.TossTarget | None, why_not: str = "") -> list:
    monkeypatch.setattr(toss_cli, "load_config", lambda: Config(places=PlacesConfig()))
    monkeypatch.setattr(target, "resolve_toss_target", lambda config, key: (doomed, why_not))
    tossed: list = []
    monkeypatch.setattr(toss_cli.teardown, "toss", lambda *a, **kw: tossed.append((a, kw)) or None)

    return tossed


def test_confirmation_is_required_by_default(monkeypatch, tmp_path, capsys):
    doomed = target.TossTarget("work", [_place(tmp_path, "feat")], from_inside=False)
    tossed = _resolves_to(monkeypatch, doomed)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args())

    assert not tossed
    assert "Nothing was torn down" in capsys.readouterr().err


def test_confirming_tears_down(monkeypatch, tmp_path):
    doomed = target.TossTarget("work", [_place(tmp_path, "feat")], from_inside=False)
    tossed = _resolves_to(monkeypatch, doomed)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    toss_cli.cmd_toss(_args())

    assert len(tossed) == 1


def test_the_set_is_shown_before_the_prompt(monkeypatch, tmp_path, capsys):
    """The list is the decision - you look at it and know whether it's right."""
    doomed = target.TossTarget(
        "stacked", [_place(tmp_path, "base"), _place(tmp_path, "on-top")], from_inside=False
    )
    _resolves_to(monkeypatch, doomed)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args())

    err = capsys.readouterr().err
    assert "session 'stacked'" in err
    assert "base" in err and "on-top" in err


def test_yes_skips_the_prompt(monkeypatch, tmp_path):
    doomed = target.TossTarget("work", [_place(tmp_path, "feat")], from_inside=False)
    tossed = _resolves_to(monkeypatch, doomed)

    def _no_input(prompt):  # pragma: no cover - reached only on a regression
        raise AssertionError("should not have prompted")

    monkeypatch.setattr("builtins.input", _no_input)

    toss_cli.cmd_toss(_args(yes=True))

    assert len(tossed) == 1


def test_json_implies_yes(monkeypatch, tmp_path):
    """There is no terminal to prompt on."""
    doomed = target.TossTarget("work", [_place(tmp_path, "feat")], from_inside=False)
    tossed = _resolves_to(monkeypatch, doomed)

    def _no_input(prompt):  # pragma: no cover - reached only on a regression
        raise AssertionError("should not have prompted")

    monkeypatch.setattr("builtins.input", _no_input)

    toss_cli.cmd_toss(_args(json=True))

    assert len(tossed) == 1


def test_json_reports_the_whole_set(monkeypatch, tmp_path, capsys):
    """A named toss acts on everything its session owns, which may surprise a caller."""
    doomed = target.TossTarget(
        "stacked",
        [_place(tmp_path, "base"), _place(tmp_path, "on-top")],
        from_inside=False,
    )
    _resolves_to(monkeypatch, doomed)

    toss_cli.cmd_toss(_args(json=True))

    reported = json.loads(capsys.readouterr().out)
    assert reported["session"] == "stacked"
    assert reported["released"] == ["base", "on-top"]


def test_unfinished_work_blocks_even_with_yes(monkeypatch, tmp_path, capsys):
    """--yes means don't ask, not throw away work I haven't pushed."""
    dirty = PlaceRoot(path=tmp_path, destroy="release {key}", inspect="echo 2 unpushed")
    doomed = target.TossTarget("work", [_place(tmp_path, "feat", dirty)], from_inside=False)
    tossed = _resolves_to(monkeypatch, doomed)

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args(yes=True))

    assert not tossed
    assert "unfinished work" in capsys.readouterr().err


def test_force_overrides_unfinished_work(monkeypatch, tmp_path):
    dirty = PlaceRoot(path=tmp_path, destroy="release {key}", inspect="echo 2 unpushed")
    doomed = target.TossTarget("work", [_place(tmp_path, "feat", dirty)], from_inside=False)
    tossed = _resolves_to(monkeypatch, doomed)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    toss_cli.cmd_toss(_args(force=True))

    assert len(tossed) == 1


def test_a_session_with_no_places_asks_only_about_the_session(monkeypatch, capsys):
    doomed = target.TossTarget("notes", [], from_inside=False)
    _resolves_to(monkeypatch, doomed)
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "y")

    toss_cli.cmd_toss(_args())

    assert prompts == ["kill it? [y/N] "]
    assert "no managed places" in capsys.readouterr().err


def test_an_unresolvable_target_exits_with_the_reason(monkeypatch, capsys):
    _resolves_to(monkeypatch, None, "Not inside tmux")

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args())

    assert "Not inside tmux" in capsys.readouterr().err


def test_a_gone_place_is_labeled_rather_than_hidden(monkeypatch, tmp_path, capsys):
    gone = ownership.Place("vanished", PlaceRoot(path=tmp_path, destroy="r {key}"), tmp_path / "x")
    _resolves_to(monkeypatch, target.TossTarget("ghost", [gone], from_inside=False))
    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    toss_cli.cmd_toss(_args())

    assert "already gone" in capsys.readouterr().err


def test_declining_at_the_prompt_by_eof_tears_nothing_down(monkeypatch, tmp_path):
    """Ctrl-D at the prompt is a no, not a yes."""
    doomed = target.TossTarget("work", [_place(tmp_path, "feat")], from_inside=False)
    tossed = _resolves_to(monkeypatch, doomed)

    def _eof(prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)

    with pytest.raises(SystemExit):
        toss_cli.cmd_toss(_args())

    assert not tossed
