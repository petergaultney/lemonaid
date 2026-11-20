from lemonaid.grove.window import settings


def test_settings_come_back_as_saved_and_start_empty(tmp_path):
    where = tmp_path / "grove-window.json"

    assert settings.load(where) == {}
    kept = {"views": {"grove": {"x": 1.5, "y": 2, "k": 9}}, "labelScales": {"grove": 0.85}}
    settings.update(kept, where)
    assert settings.load(where) == kept


def test_an_unreadable_settings_file_is_ignored(tmp_path):
    where = tmp_path / "grove-window.json"
    where.write_text("{not json")

    assert settings.load(where) == {}


def test_the_window_keeps_its_settings_beside_the_layout():
    assert settings.path().name == "grove-window.json"
    assert settings.path().parent == settings.state.path().parent


def test_the_pages_saves_and_the_windows_frames_keep_each_other(tmp_path):
    where = tmp_path / "grove-window.json"

    settings.keep_frame("laptop", [0, 0, 800, 600], where)
    settings.update({"views": {"1720x920": {}}, "labelScales": {}}, where)
    settings.keep_frame("desk", [1728, 0, 1200, 900], where)

    assert settings.frame("laptop", where) == [0, 0, 800, 600]
    assert settings.frame("desk", where) == [1728, 0, 1200, 900]
    assert settings.frame("train", where) is None
    assert settings.load(where)["views"] == {"1720x920": {}}


def test_a_display_set_forgotten_goes_back_over_the_terminal_and_the_rest_stay(tmp_path):
    where = tmp_path / "grove-window.json"
    settings.keep_frame("laptop", [0, 0, 800, 600], where)
    settings.keep_frame("desk", [1728, 0, 1200, 900], where)

    settings.forget_frame("desk", where)
    assert settings.frame("desk", where) is None
    assert settings.frame("laptop", where) == [0, 0, 800, 600]
