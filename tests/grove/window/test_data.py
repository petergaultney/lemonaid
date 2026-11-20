from lemonaid.config import load_config
from lemonaid.grove.layout import state
from lemonaid.grove.source import blocks, live
from lemonaid.grove.window import data
from tests.grove.shared import block, plot_data, stream_saved, tree


def _grove(monkeypatch):
    monkeypatch.setattr(blocks, "blocks", lambda *_args: (block("a", "1", tree("s"), tree("t")),))
    state.save({"version": state.VERSION} | stream_saved({"a": plot_data(2, 2, 60, 14)}))
    live.fresh(load_config(), None)  # saves the trees' spots, as an open grove would have
    return data.load(load_config())


def test_a_dropped_tree_is_saved_where_it_was_dropped(monkeypatch):
    grove = _grove(monkeypatch)
    s = state.load()["trees"]["a"]["s"]
    x, y = s["x"] + 2, s["y"]

    assert data.refusal(grove, "1", "s", x, y) == ""
    assert data.plant(grove, "1", "s", x, y) == ""
    assert (state.load()["trees"]["a"]["s"]["x"], state.load()["trees"]["a"]["s"]["y"]) == (x, y)


def test_a_tree_dropped_on_another_or_off_its_block_is_refused_and_not_saved(monkeypatch):
    grove = _grove(monkeypatch)
    before = state.load()
    s = before["trees"]["a"]["s"]

    assert "stands there" in data.plant(grove, "1", "t", s["x"], s["y"])
    assert data.refusal(grove, "1", "t", 500, 3)
    assert data.refusal(grove, "9", "t", 3, 3) == "that tree is gone"
    assert state.load() == before


def test_the_window_shows_what_grove_show_json_prints_with_colors_leads_and_landmarks(monkeypatch):
    shown = data.shown(_grove(monkeypatch))

    first = shown["blocks"][0]
    assert first["color"] == "#6495ed"
    assert {"lead", "size", "bay", "spot"} <= set(first["trees"][0])
    assert shown["stream"] and shown["roads"] == []
    assert shown["summary"] == "2 lemons on 2 trees · 0 mid-turn"
    assert "".join(text for text, *_ in shown["attention"]).strip()  # the terminal's chips, as runs
    assert all(
        color.startswith("#") and fill.startswith("#") for _, color, fill, _ in shown["attention"]
    )


def test_a_tree_no_grove_has_saved_yet_can_be_dropped(monkeypatch):
    monkeypatch.setattr(blocks, "blocks", lambda *_args: (block("a", "1", tree("s")),))
    state.save({"version": state.VERSION} | stream_saved({"a": plot_data(2, 2, 60, 14)}))
    grove = data.load(load_config())  # read only: the tree's spot isn't saved
    standing = grove.arrangement.trees[("a", "s")]
    x, y = standing.cx + 2, standing.cy

    assert "s" not in state.load()["trees"].get("a", {})
    assert data.refusal(grove, "1", "s", x, y) == ""
    assert data.plant(grove, "1", "s", x, y) == ""
    assert (state.load()["trees"]["a"]["s"]["x"], state.load()["trees"]["a"]["s"]["y"]) == (x, y)


def test_a_block_moved_or_resized_is_saved_there(monkeypatch):
    grove = _grove(monkeypatch)

    assert data.reframe(grove, "1", [], 5, 2) == ""
    plot = state.load()["plots"]["a"]
    assert (plot["x"], plot["y"], plot["w"], plot["h"]) == (7, 4, 60, 14)

    assert data.reframe(data.load(load_config()), "1", ["right", "bottom"], 6, 3) == ""
    plot = state.load()["plots"]["a"]
    assert (plot["x"], plot["y"], plot["w"], plot["h"]) == (7, 4, 66, 17)


def test_a_block_moved_onto_the_stream_or_shrunk_too_far_is_refused_and_not_saved(monkeypatch):
    grove = _grove(monkeypatch)
    before = state.load()

    assert "stream" in data.reframe(grove, "1", [], 0, 20)
    assert "12 columns" in data.block_refusal(grove, "1", ["right"], -50, 0)
    assert data.block_refusal(grove, "9", [], 1, 1) == "that block is gone"
    assert state.load() == before


def test_a_block_no_grove_has_saved_yet_can_be_moved_and_resized(monkeypatch):
    monkeypatch.setattr(blocks, "blocks", lambda *_args: (block("a", "1", tree("s")),))
    grove = data.load(load_config())  # read only: no layout is saved
    was = grove.arrangement.plots["a"]

    assert not state.path().exists()
    assert data.reframe(grove, "1", [], 2, 0) == ""
    assert data.reframe(data.load(load_config()), "1", ["right"], 3, 0) == ""
    plot = state.load()["plots"]["a"]
    assert (plot["x"], plot["y"], plot["w"], plot["h"]) == (was.x + 2, was.y, was.w + 3, was.h)


def test_a_lead_tree_can_be_moved_farther_from_the_packhouse(
    monkeypatch,
):
    monkeypatch.setattr(
        blocks,
        "blocks",
        lambda *_args: (
            block("west", "1", tree("one"), tree("head", lead=True)),
            block("", "0", tree("hq")),
        ),
    )
    house = plot_data(140, 15, 24, 7, roundness=12.0, seed=0, texture="house")
    state.save(
        {"version": state.VERSION} | stream_saved({"west": plot_data(10, 5, 90, 30), "": house})
    )
    live.fresh(load_config(), None)
    grove = data.load(load_config())
    head = grove.arrangement.trees[("west", "head")]
    away = (head.cx - 30, head.cy)  # the packhouse is to the east

    assert data.refusal(grove, "1", "head", *away) == ""
    assert data.plant(grove, "1", "head", *away) == ""
    lead = data.load(load_config()).arrangement.trees[("west", "head")]
    assert (lead.cx, lead.cy) == away


def test_search_finds_lemons_as_the_terminal_grove_does_with_their_trees_letters(monkeypatch):
    grove = _grove(monkeypatch)

    found = data.search(grove, "t")
    assert [(m["digit"], m["key"], m["index"]) for m in found] == [("1", "t", 0)]
    assert found[0]["letter"] == grove.arrangement.trees[("a", "t")].letter
    assert data.search(grove, "  ") == []


def test_the_window_gets_each_trees_flip_key_line(monkeypatch):
    tree = data.shown(_grove(monkeypatch))["blocks"][0]["trees"][0]

    assert tree["stats"].startswith("0/1")


def test_open_ground_moves_and_resizes_like_a_block(monkeypatch):
    monkeypatch.setattr(blocks, "blocks", lambda *_args: (block("a", "1", tree("s")),))
    plots = {"a": plot_data(2, 2, 60, 14), "gone": plot_data(70, 2, 40, 12)}
    state.save({"version": state.VERSION} | stream_saved(plots))
    live.fresh(load_config(), None)  # marks the ended group's plot open
    grove = data.load(load_config())
    assert len(grove.arrangement.open) == 1

    assert data.block_refusal(grove, "open:0", [], 3, 0) == ""
    assert data.reframe(grove, "open:0", ["right"], 4, 0) == ""
    assert data.load(load_config()).arrangement.open[0].w == 44
    assert data.block_refusal(grove, "open:5", [], 1, 0) == "that block is gone"
