from lemonaid import groups
from lemonaid.config import load_config
from lemonaid.grove import grafts
from lemonaid.grove.layout import state
from lemonaid.grove.source import blocks, live
from lemonaid.grove.window import data, edits
from lemonaid.inbox import db, pins
from tests.grove.shared import block, lemon, plot_data, stream_saved, tree


def _grove(monkeypatch):
    with db.connect() as conn:
        for name in ("one", "two"):
            db.add(
                conn, f"claude:{name}", "a message", name, {"tty": f"/dev/ttys5{len(name)}{name}"}
            )
        groups.store.create(conn, "a")
        groups.store.create(conn, "b")
        groups.store.add(conn, groups.store.find(conn, "b"), ["claude:two"])
    two = tree("s", lemon("claude:one"), lemon("claude:two"))
    monkeypatch.setattr(blocks, "blocks", lambda *_args, **_kw: (block("a", "1", two),))
    state.save({"version": state.VERSION} | stream_saved({"a": plot_data(2, 2, 60, 14)}))
    live.fresh(load_config(), None)
    return data.load(load_config())


def test_the_dialog_learns_what_an_edit_changes_and_its_choices(monkeypatch):
    grove, config = _grove(monkeypatch), load_config()

    whole = edits.info(grove, config, "pin", "1", "s", "")
    assert whole["problem"] == "" and whole["what"] == "pinning or unpinning all 2 lemons on s"
    assert edits.info(grove, config, "snooze", "1", "s", "claude:one")["presets"]
    assert edits.info(grove, config, "group", "1", "s", "claude:one")["groups"] == ["b"]
    assert edits.info(grove, config, "pin", "9", "s", "")["problem"] == "that block is gone"
    assert (
        edits.info(grove, config, "pin", "1", "s", "claude:gone")["problem"] == "that lemon is gone"
    )


def test_edits_change_one_lemon_or_the_whole_tree(monkeypatch):
    grove, config = _grove(monkeypatch), load_config()

    assert edits.make(grove, config, "pin", "1", "s", "", "", None) == "pinned 2 lemons"
    assert edits.make(grove, config, "pin", "1", "s", "claude:one", "", None) == "unpinned 1 lemon"
    with db.connect() as conn:
        assert not pins.is_pinned(conn, "claude:one") and pins.is_pinned(conn, "claude:two")
    assert edits.make(grove, config, "snooze", "1", "s", "claude:one", "soon", None) == (
        "Enter a duration like 45m, 2h, 3d or 1w, or 'morning'"
    )
    assert (
        edits.make(grove, config, "snooze", "1", "s", "claude:one", "2h", None) == "snoozed 1 lemon"
    )
    assert (
        edits.make(grove, config, "group", "1", "s", "claude:one", "b", None)
        == 'moved 1 lemon to "b"'
    )
    assert (
        edits.make(grove, config, "archive", "1", "s", "claude:two", "", None) == "archived 1 lemon"
    )
    assert edits.make(grove, config, "color", "1", "", "", "teal", None) == 'recolored "a"'
    assert edits.make(grove, config, "burn", "1", "s", "", "", None) == "no edit burn"


def test_a_graft_offers_the_other_trees_and_makes_the_shared_change(monkeypatch):
    with db.connect() as conn:
        for name in ("one", "three"):
            db.add(conn, f"claude:{name}", "a message", name, {"tty": f"/dev/ttys6{name}"})
        groups.store.create(conn, "a")
    trees = (tree("s", lemon("claude:one")), tree("t", lemon("claude:three")))
    monkeypatch.setattr(blocks, "blocks", lambda *_args, **_kw: (block("a", "1", *trees),))
    state.save({"version": state.VERSION} | stream_saved({"a": plot_data(2, 2, 60, 14)}))
    live.fresh(load_config(), None)
    grove, config = data.load(load_config()), load_config()
    letter = grove.arrangement.trees[("a", "t")].letter

    info = edits.info(grove, config, "graft", "1", "s", "claude:one")
    assert info["trees"] == [["claude:three", f"1{letter} t"]]
    assert info["what"] == "grafting lemon lemon claude:one"
    assert edits.make(grove, config, "graft", "1", "s", "claude:one", "claude:three", None) == (
        "grafted 1 lemon onto claude:three"
    )
    with db.connect() as conn:
        assert grafts.recorded(conn) == {"claude:one": "claude:three"}
