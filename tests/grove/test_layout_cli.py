import json
import sys

import pytest

from lemonaid import cli
from lemonaid.grove.layout import state
from lemonaid.grove.source import blocks
from tests.grove.shared import block, plot_data, stream_saved, tree


def _run(monkeypatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["lemonaid", "grove", *args])
    cli.main()


def _saved() -> dict:
    return {"version": state.VERSION} | stream_saved(
        {"a": plot_data(2, 2, 30, 10), "b": plot_data(60, 2, 30, 10)}
    )


def test_a_group_the_saved_layout_has_not_seen_is_placed_from_the_proposal(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(blocks, "blocks", lambda *_args: (block("a", "1", tree("t")),))
    proposed = tmp_path / "proposed.json"

    _run(monkeypatch, "propose", str(proposed))
    _run(monkeypatch, "move", "1", "150", "45", "--layout", str(proposed))

    assert "a" not in state.load()["plots"]

    _run(monkeypatch, "apply", str(proposed), "--json")

    assert json.loads(capsys.readouterr().out.splitlines()[-1])["applied"] == ["a"]
    assert (state.load()["plots"]["a"]["x"], state.load()["plots"]["a"]["y"]) == (150, 45)


def test_a_refused_apply_leaves_the_grove_alone(monkeypatch, tmp_path, capsys):
    live_blocks = (block("a", "1", tree("s")), block("b", "2", tree("t")))
    monkeypatch.setattr(blocks, "blocks", lambda *_args: live_blocks)
    state.save(_saved())
    proposed = tmp_path / "proposed.json"
    state.save(stream_saved({"a": plot_data(50, 2, 30, 10)}), proposed)

    with pytest.raises(SystemExit):
        _run(monkeypatch, "apply", str(proposed))

    assert "a and b" in capsys.readouterr().err
    assert state.load() == _saved()


def test_a_layout_must_exist(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit):
        _run(monkeypatch, "move", "a", "1", "1", "--layout", str(tmp_path / "missing.json"))

    assert "grove propose" in capsys.readouterr().err


def test_plant_stands_a_tree_in_the_proposal_and_refuses_one_on_another(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(blocks, "blocks", lambda *_args: (block("a", "1", tree("s"), tree("t")),))
    proposed = tmp_path / "proposed.json"
    _run(monkeypatch, "propose", str(proposed))
    spots = state.load(proposed)["trees"]["a"]
    x, y = spots["s"]["x"] + 1, spots["s"]["y"]

    _run(monkeypatch, "plant", "a", "s", str(x), str(y), "--layout", str(proposed))

    assert (state.load(proposed)["trees"]["a"]["s"]["x"], state.load()["plots"]) == (x, {})
    with pytest.raises(SystemExit):
        _run(monkeypatch, "plant", "a", "t", str(x), str(y), "--layout", str(proposed))
    assert "can't stand at" in capsys.readouterr().err


def test_a_tree_off_a_rounded_corner_is_refused_by_plant_and_apply(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(blocks, "blocks", lambda *_args: (block("a", "1", tree("t")),))
    state.save(
        {"version": state.VERSION} | stream_saved({"a": plot_data(2, 2, 40, 20, roundness=1.5)})
    )
    proposed = tmp_path / "proposed.json"
    _run(monkeypatch, "propose", str(proposed))
    before = proposed.read_text()

    with pytest.raises(SystemExit):
        _run(monkeypatch, "plant", "a", "t", "5", "0", "--layout", str(proposed))

    assert proposed.read_text() == before
    layout = state.load(proposed)
    layout["trees"]["a"]["t"].update(x=5, y=0)
    state.save(layout, proposed)
    live = state.load()
    with pytest.raises(SystemExit):
        _run(monkeypatch, "apply", str(proposed))
    assert state.load() == live
    assert capsys.readouterr().err.count("off its block's ground") == 2


def test_apply_leaves_an_untouched_packhouse_alone(monkeypatch, tmp_path, capsys):
    grove_blocks = (
        block("", "0", tree("hq"), tree("misc")),
        block("a", "1", tree("s"), tree("t"), tree("u")),
    )
    monkeypatch.setattr(blocks, "blocks", lambda *_args: grove_blocks)
    proposed = tmp_path / "proposed.json"
    _run(monkeypatch, "propose", str(proposed))
    state.save(state.load(proposed))  # the live grove laid out as the proposal was
    spot = state.load(proposed)["trees"]["a"]["s"]
    _run(
        monkeypatch,
        "plant",
        "1",
        "s",
        str(spot["x"] + 1),
        str(spot["y"]),
        "--layout",
        str(proposed),
    )
    for where in (None, proposed):  # a bay on the packhouse's edge, off its rounded ground
        layout = state.load(where)
        layout["trees"][""]["misc"]["x"] = layout["plots"][""]["w"]
        state.save(layout, where)

    _run(monkeypatch, "apply", str(proposed), "--json")

    assert json.loads(capsys.readouterr().out.splitlines()[-1])["error"] is None


def test_reshape_refuses_corners_rounded_out_from_under_a_tree(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(blocks, "blocks", lambda *_args: (block("a", "1", tree("t")),))
    state.save(
        {"version": state.VERSION} | stream_saved({"a": plot_data(2, 2, 40, 20, roundness=12)})
    )
    proposed = tmp_path / "proposed.json"
    _run(monkeypatch, "propose", str(proposed))
    _run(monkeypatch, "plant", "a", "t", "5", "1", "--layout", str(proposed))
    before = proposed.read_text()

    with pytest.raises(SystemExit):
        _run(monkeypatch, "reshape", "a", "1.5", "--layout", str(proposed))

    assert proposed.read_text() == before
    assert "keep its corners squarer" in capsys.readouterr().err


def test_plant_refuses_moving_a_lead_away_from_the_packhouse(monkeypatch, tmp_path, capsys):
    grove_blocks = (block("", "0", tree("hq")), block("a", "1", tree("l", lead=True), tree("s")))
    monkeypatch.setattr(blocks, "blocks", lambda *_args: grove_blocks)
    proposed = tmp_path / "proposed.json"
    _run(monkeypatch, "propose", str(proposed))
    layout = state.load(proposed)
    house, plot, lead = layout["plots"][""], layout["plots"]["a"], layout["trees"]["a"][":lead"]
    away = 1 if plot["x"] + lead["x"] > house["x"] + house["w"] / 2 else -1
    before = proposed.read_text()

    with pytest.raises(SystemExit):
        _run(
            monkeypatch,
            "plant",
            "1",
            "l",
            str(lead["x"] + away),
            str(lead["y"]),
            "--layout",
            str(proposed),
        )

    assert proposed.read_text() == before
    assert "nearest the packhouse" in capsys.readouterr().err
