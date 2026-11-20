from lemonaid.grove.window import settings


def test_settings_come_back_as_saved_and_start_empty(tmp_path):
    where = tmp_path / "grove-window.json"

    assert settings.load(where) == {}
    kept = {"views": {"grove": {"x": 1.5, "y": 2, "k": 9}}, "labelScales": {"grove": 0.85}}
    settings.save(kept, where)
    assert settings.load(where) == kept


def test_an_unreadable_settings_file_is_ignored(tmp_path):
    where = tmp_path / "grove-window.json"
    where.write_text("{not json")

    assert settings.load(where) == {}


def test_the_window_keeps_its_settings_beside_the_layout():
    assert settings.path().name == "grove-window.json"
    assert settings.path().parent == settings.state.path().parent
