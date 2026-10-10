"""A card's second line: the project in place of a cwd that mostly repeats the branch."""

from rich.console import Console
from rich.text import Text

from lemonaid.config import PlaceRoot, PlacesConfig, load_config
from lemonaid.inbox.tui import app, brief_cards, card_context, utils
from lemonaid.inbox.tui.utils import project_color
from lemonaid.tmux import window_status

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


def test_project_name_color_is_stable_and_only_styles_the_project_name(tmp_path):
    cwd = tmp_path / "ds-monorepo" / "p"
    where = card_context.project_part(_places(tmp_path), str(cwd), "main", "apps/ua")

    def project_part():
        return card_context.parts(
            ("project",), _TIME, where, "main", str(cwd), True, project_name_colors=True
        )[0]

    first = project_part().text
    second = project_part().text

    assert first.plain == "ds-monorepo: apps/ua"
    assert first.spans == second.spans
    assert first.spans[0].style == project_color("ds-monorepo")
    assert (first.spans[0].start, first.spans[0].end) == (0, len("ds-monorepo"))
    assert first.style.startswith("bold ")


def test_project_colors_match_tmux_window_labels():
    for name in ("ds-monorepo", "apps", "libs", "mops", "pantry"):
        assert project_color(name) == window_status.get_color(name)
    assert len({project_color(f"project-{n}") for n in range(50)}) > 6


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


def test_the_time_goes_before_the_project_name_is_cut(tmp_path):
    cwd = tmp_path / "ds-monorepo" / "p"

    assert _line(tmp_path, cwd, "b", "apps/unified-asset", width=15) == "ds-monorepo"


def test_a_narrow_card_keeps_a_project_name_that_fits_alone(tmp_path):
    places = PlacesConfig(roots=[PlaceRoot(path=tmp_path / "engineering-backend")])
    cwd = str(tmp_path / "engineering-backend" / "x")
    line = card_context.parts(
        ("time", "project", "branch"),
        _TIME,
        card_context.project_part(places, cwd, "x"),
        "x",
        cwd,
        is_unread=False,
    )
    cells = [_TIME, Text(""), Text(""), Text("n"), Text("x"), Text(cwd), Text("m")]

    (body,) = app._as_card(cells, 21, context_parts=line)

    assert body.plain.split("\n")[1].strip() == "engineering-backend"


def test_the_cwd_fallback_keeps_the_projects_place(tmp_path):
    line = _line(tmp_path, tmp_path / "notes", "", fields=("project", "time", "cwd"))

    assert line.endswith("/notes · 15:32:47")


def test_the_cwd_fallback_keeps_the_projects_place_after_the_cwd(tmp_path):
    line = _line(tmp_path, tmp_path / "notes", "", fields=("cwd", "time", "project"))

    assert line.startswith("15:32:47 · ") and line.count("notes") == 1


def test_the_age_field_shows_the_brief_age_in_place_of_the_time(tmp_path):
    cwd = tmp_path / "pantry"
    where = card_context.project_part(_places(tmp_path), str(cwd), "main")
    fields = ("age", "project", "branch")

    def line(age: str) -> str:
        parts = card_context.parts(fields, _TIME, where, "main", str(cwd), False, age)
        return card_context.fitted(parts, 200).plain

    assert line("idle 3 days") == "idle 3 days · pantry · main"
    assert line("") == "15:32:47 · pantry · main"


def test_inline_age_keeps_the_held_status_color():
    where = card_context.Part("project", Text("pantry"))
    age = brief_cards.CardBrief("blocked", "", 0, mid_turn=True, held_mid_turn=True).age_text(60, 6)
    (part,) = card_context.parts(("age",), _TIME, where, "main", "/pantry", False, age)
    console = Console(color_system="truecolor")
    status_style = part.text.get_style_at_offset(console, 0)
    age_offset = part.text.plain.index("updated")
    age_style = part.text.get_style_at_offset(console, age_offset)

    assert part.text.plain == "blocked · updated 1m ago"
    assert status_style.color.name == utils.ATTENTION_COLOR
    assert age_style.color.name == utils.FIELD_STYLES["time"]


def test_inline_age_keeps_held_status_color_with_neutral_timing():
    where = card_context.Part("project", Text("pantry"))
    age = brief_cards.CardBrief("blocked", "", 0, mid_turn=True, held_mid_turn=True).age_text(60, 6)
    (part,) = card_context.parts(
        ("age",), _TIME, where, "main", "/pantry", False, age, neutral_timing=True
    )
    console = Console(color_system="truecolor")
    status_style = part.text.get_style_at_offset(console, 0)
    age_style = part.text.get_style_at_offset(console, part.text.plain.index("updated"))

    assert status_style.color.name == utils.ATTENTION_COLOR
    assert age_style.color.name == "bright_black"


def test_a_narrow_card_keeps_the_age_and_cuts_the_project_instead(tmp_path):
    cwd = tmp_path / "engineering-backend"
    where = card_context.project_part(_places(tmp_path), str(cwd), "main")
    age = "idle 4 days (stale)"
    for fields in (("age", "project", "branch"), ("project", "age", "branch")):
        parts = card_context.parts(fields, _TIME, where, "main", str(cwd), False, age)
        line = card_context.fitted(parts, 31)
        line.truncate(31, overflow="ellipsis")

        assert line.plain.startswith(age), fields
