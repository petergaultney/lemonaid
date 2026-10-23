from lemonaid.grove.layout import view


def test_the_view_comes_back_where_it_was_left(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    assert view.load() == (0, 0)
    view.save((40, 8))
    assert view.load() == (40, 8)


def test_an_unreadable_view_starts_at_the_top_left(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path))
    (tmp_path / "grove-view.json").write_text("{nope")
    assert view.load() == (0, 0)
