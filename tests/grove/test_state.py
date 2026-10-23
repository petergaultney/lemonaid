from lemonaid.grove.layout import state


def test_a_missing_layout_loads_empty(tmp_path):
    assert state.load(tmp_path / "grove.json") == {
        "version": state.VERSION,
        "plots": {},
        "trees": {},
    }


def test_an_unreadable_layout_loads_empty(tmp_path):
    (tmp_path / "grove.json").write_text("{not json")
    assert state.load(tmp_path / "grove.json")["plots"] == {}


def test_roads_and_stream_survive_a_save(tmp_path):
    where = tmp_path / "sub" / "grove.json"
    saved = {
        "version": state.VERSION,
        "plots": {"relay": {"x": 1}},
        "trees": {},
        "roads": [[[0, 1], [2, 3]]],
        "stream": [[0, 5], [9, 6]],
    }
    state.save(saved, where)
    assert state.load(where) == saved
    assert not list(where.parent.glob("*.tmp"))


def test_the_layout_lives_in_the_state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    assert state.path() == tmp_path / "grove.json"
