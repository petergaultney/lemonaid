import json
import sys

from lemonaid import cli
from lemonaid.grove.layout import arrange, compact, screen_size
from lemonaid.grove.source import blocks
from tests.grove.shared import NOW, block, plot_data, stream_saved, tree

_SIZE = (214, 63)


def _placed() -> list[compact.Placed]:
    grove = block("a", "1", tree("s"), tree("t"))
    saved = stream_saved(
        {"a": plot_data(20, 2, 120, 26)},
        {"a": {"s": {"letter": "s", "x": 20, "y": 6}, "t": {"letter": "t", "x": 80, "y": 16}}},
    )
    return compact.placed(grove, arrange.arrange((grove,), saved, NOW)[0], _SIZE)


def test_each_tree_gets_its_spot_trunk_and_list_on_the_zoomed_screen():
    placed = _placed()

    assert [p.letter for p in placed] == ["s", "t"]
    assert all(len(p.list) == 4 and not p.off for p in placed)
    assert all(0 < p.center[0] < _SIZE[0] and 0 < p.center[1] < _SIZE[1] for p in placed)


def test_the_last_grove_screen_size_is_the_default_for_show(monkeypatch, capsys):
    monkeypatch.setattr(blocks, "blocks", lambda *_args: (block("a", "1", tree("t")),))
    assert screen_size.last() is None

    screen_size.record((120, 40))
    monkeypatch.setattr(sys, "argv", ["lemonaid", "grove", "show", "--json"])
    cli.main()

    assert json.loads(capsys.readouterr().out)["screen"] == [120, 40]


def test_show_compact_prints_a_line_per_tree(monkeypatch, capsys):
    monkeypatch.setattr(blocks, "blocks", lambda *_args: (block("a", "1", tree("t")),))
    monkeypatch.setattr(sys, "argv", ["lemonaid", "grove", "show", "1", "--compact"])
    cli.main()

    out = capsys.readouterr().out.splitlines()

    assert out[0].startswith("Block 1 (a) zoomed at ") and "1t t: spot " in out[1]


def test_the_packhouse_has_no_trees_to_place():
    grove = block("", "0", tree("h"))
    saved = stream_saved({"": plot_data(60, 20, 40, 12, texture="house")})
    arrangement = arrange.arrange((grove,), saved, NOW)[0]

    assert compact.placed(grove, arrangement, _SIZE) == []
