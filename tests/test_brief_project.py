"""The project a brief card leads with, from place roots, the place, and the brief's Area line."""

from lemonaid.brief import project, status
from lemonaid.config import PlaceRoot


def test_a_worktree_under_a_root_is_named_for_the_root(tmp_path):
    roots = [PlaceRoot(path=tmp_path / "ds-monorepo")]
    place = tmp_path / "ds-monorepo" / "mops" / "fix"

    assert project.label(roots, str(place), str(place)) == "ds-monorepo"


def test_a_roots_name_wins_over_its_directory(tmp_path):
    roots = [PlaceRoot(path=tmp_path / "lemonaid-wt", name="lemonaid")]
    place = tmp_path / "lemonaid-wt" / "brief" / "project-header"

    assert project.label(roots, str(place), str(place)) == "lemonaid"


def test_the_innermost_root_names_it(tmp_path):
    roots = [PlaceRoot(path=tmp_path), PlaceRoot(path=tmp_path / "relay")]

    assert project.label(roots, str(tmp_path / "relay" / "x"), "") == "relay"


def test_outside_every_root_the_place_names_itself(tmp_path):
    assert project.label([], str(tmp_path / "scratch"), "") == "scratch"


def test_the_area_follows_the_name(tmp_path):
    roots = [PlaceRoot(path=tmp_path / "ds-monorepo")]
    place = tmp_path / "ds-monorepo" / "ua" / "fix"

    assert project.label(roots, str(place), str(place), "apps/unified-asset") == (
        "ds-monorepo: apps/unified-asset"
    )


def test_without_an_area_a_cwd_below_the_place_is_the_part(tmp_path):
    place = tmp_path / "ds-monorepo" / "ua" / "fix"
    roots = [PlaceRoot(path=tmp_path / "ds-monorepo")]

    assert project.label(roots, str(place), str(place / "apps" / "unified-asset")) == (
        "ds-monorepo: apps/unified-asset"
    )


def test_the_area_line_is_read_only_above_the_first_section():
    text = "# Task\n\nStatus: working\n\nArea: libs/mops\n\n## Goal\n\nArea: not this\n"

    assert status.split(text).area == "libs/mops"
    assert status.split("# Task\n\n## Goal\n\nArea: prose\n").area == ""


def test_the_area_line_is_left_out_of_the_body_the_card_already_shows_it():
    parts = status.split("# Task\n\nStatus: working\n\nArea: libs/mops\n\nParent: hq, 2026-10-01\n")

    assert "Area:" not in parts.rest
    assert "Parent: hq" in parts.rest
