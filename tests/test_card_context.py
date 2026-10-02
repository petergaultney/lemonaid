"""A card's second line: the project in place of a cwd that mostly repeats the branch."""

from rich.text import Text

from lemonaid.config import PlaceRoot, PlacesConfig, load_config
from lemonaid.inbox.tui import card_context

_TIME = Text("15:32:47")


def _places(tmp_path) -> PlacesConfig:
    return PlacesConfig(roots=[PlaceRoot(path=tmp_path / "ds-monorepo")])


def _line(tmp_path, cwd, branch, area="", fields=("time", "project", "branch"), width=200):
    where = card_context.project_part(_places(tmp_path), str(cwd), branch, area)
    parts = card_context.parts(fields, _TIME, where, branch, str(cwd), is_unread=False)
    return card_context.fitted(parts, width).plain


def test_a_place_under_a_root_shows_the_root_and_its_area(tmp_path):
    cwd = tmp_path / "ds-monorepo" / "ua" / "fix"

    assert _line(tmp_path, cwd, "ua/fix", "apps/unified-asset") == (
        "15:32:47 · ds-monorepo: apps/unified-asset · ua/fix"
    )


def test_outside_every_root_a_branch_names_the_directory(tmp_path):
    assert _line(tmp_path, tmp_path / "pantry", "main") == "15:32:47 · pantry · main"


def test_with_no_root_and_no_branch_the_cwd_stays(tmp_path):
    assert _line(tmp_path, tmp_path / "notes", "").endswith("/notes")


def test_the_cwd_fallback_is_not_shown_twice(tmp_path):
    line = _line(tmp_path, tmp_path / "notes", "", fields=("project", "cwd"))

    assert line.count("notes") == 1


def test_fields_come_in_the_configured_order(tmp_path):
    cwd = tmp_path / "ds-monorepo" / "x"

    assert _line(tmp_path, cwd, "x", fields=("branch", "project")) == "x · ds-monorepo"


def test_the_branch_is_cut_first(tmp_path):
    cwd = tmp_path / "ds-monorepo" / "p"
    line = _line(tmp_path, cwd, "protostellar/log-model-call-usage", "apps/ua", width=40)

    assert line == "15:32:47 · ds-monorepo: apps/ua · proto…"


def test_a_branch_too_short_to_read_drops_out(tmp_path):
    cwd = tmp_path / "ds-monorepo" / "p"
    line = _line(tmp_path, cwd, "protostellar/log", "apps/ua", width=34)

    assert line == "15:32:47 · ds-monorepo: apps/ua"


def test_then_the_area_and_never_the_project_name(tmp_path):
    cwd = tmp_path / "ds-monorepo" / "p"

    assert (
        _line(tmp_path, cwd, "b", "apps/unified-asset", width=28) == "15:32:47 · ds-monorepo: app…"
    )
    assert _line(tmp_path, cwd, "b", "apps/unified-asset", width=22) == "15:32:47 · ds-monorepo"


def test_unknown_card_fields_are_dropped_with_a_warning(tmp_path, capsys):
    config = tmp_path / "config.toml"
    config.write_text('[tui]\ncard_fields = ["project", "where", "branch"]\n')

    assert load_config(config).tui.card_fields == ("project", "branch")
    assert "'where'" in capsys.readouterr().err
