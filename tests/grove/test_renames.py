from lemonaid.grove.layout import state
from lemonaid.grove.source import renames
from lemonaid.grove.tui.picking import Target
from lemonaid.inbox import db


def _renamer(calls: list[tuple[str, str]], refusal: str = ""):
    def rename_session(old: str, new: str) -> str:
        calls.append((old, new))
        return refusal

    return rename_session


def _saved(where):
    state.save(
        {
            "version": state.VERSION,
            "plots": {},
            "trees": {
                "a": {"old": {"x": 1, "y": 1, "letter": "o"}},
                "b": {"old": {"x": 9, "y": 9, "letter": "o"}},
            },
        },
        where,
    )


def test_a_session_rename_keeps_the_spot_and_letter_in_every_group(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    _saved(state.path())
    calls: list[tuple[str, str]] = []
    note = renames.apply(Target("rename", "a", ("a", "b"), "old", "", "new", ()), _renamer(calls))
    assert note == "renamed session old to new"
    assert calls == [("old", "new")]
    trees = state.load()["trees"]
    assert trees["a"] == {"new": {"x": 1, "y": 1, "letter": "o"}}
    assert trees["b"] == {"new": {"x": 9, "y": 9, "letter": "o"}}


def test_a_refused_rename_leaves_the_layout_as_it_was(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    _saved(state.path())
    refused = _renamer([], "tmux could not rename old")
    assert "could not rename" in renames.apply(
        Target("rename", "a", ("a", "b"), "old", "", "new", ()), refused
    )
    assert set(state.load()["trees"]["a"]) == {"old"}


def test_without_a_session_renamer_a_session_is_not_renamed():
    assert "needs" in renames.apply(Target("rename", "a", ("a",), "old", "", "new", ()))


def test_a_session_rename_renames_the_lemon_its_tag_shows(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    _saved(state.path())
    with db.connect() as conn:
        db.add(conn, "claude:tagged", "a message", "old", {"tty": "/dev/ttys7001"})
        found = db.get_by_channel(conn, "claude:tagged", unread_only=False)
        db.update_name(conn, found.id, "Spatial lemon jump")
    target = Target(
        "rename",
        "a",
        ("a", "b"),
        "old",
        "",
        "Lemon grove map",
        (("claude:tagged", "1"),),
        tagged="claude:tagged",
    )
    renames.apply(target, _renamer([]))
    with db.connect() as conn:
        assert db.get_by_channel(conn, "claude:tagged", unread_only=False).name == "Lemon grove map"
