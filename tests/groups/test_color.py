import sqlite3

import pytest

from lemonaid import groups
from lemonaid.inbox import db


def test_a_color_is_saved_as_lowercase_rrggbb_from_any_css_form():
    assert groups.color.parsed("#B8336A") == "#b8336a"
    assert groups.color.parsed(" teal ") == "#008080"
    assert groups.color.parsed("#abc") == "#aabbcc"
    assert groups.color.parsed("") == ""


@pytest.mark.parametrize("text", ["nope", "ansi_red", "transparent"])
def test_anything_but_an_opaque_rgb_color_is_refused(text):
    with pytest.raises(groups.store.GroupError, match="isn't a color"):
        groups.color.parsed(text)


def test_a_saved_color_outranks_the_config_which_outranks_the_palette():
    with db.connect() as conn:
        saved = groups.color.save(conn, groups.store.create(conn, "saved"), "#112233")
        configured = groups.store.create(conn, "configured")
        automatic = groups.store.create(conn, "automatic")

        drawn = groups.color.drawn(
            [saved, configured, automatic], {"saved": "#445566", "configured": "#778899"}
        )

    assert drawn["saved"] == "#112233"
    assert drawn["configured"] == "#778899"
    assert drawn["automatic"] not in {"#112233", "#778899", ""}


def test_a_saved_color_follows_a_rename_and_clears():
    with db.connect() as conn:
        group = groups.color.save(conn, groups.store.create(conn, "old"), "#112233")
        renamed = groups.store.rename(conn, group, "new")
        assert renamed.saved_color == "#112233"
        assert groups.color.save(conn, renamed, "").saved_color == ""


def _before(path, version: int, *statements: str) -> None:
    """*path* as a database at *version*, with no color column, changed by *statements*."""
    with db.connect(path) as conn:
        groups.store.create(conn, "lemonaid")
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE lemon_groups DROP COLUMN color")
    for statement in statements:
        conn.execute(statement)
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()
    db._initialized_dbs.discard(path)


def _columns(conn) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(lemon_groups)")}


_ADD_COLOUR = "ALTER TABLE lemon_groups ADD COLUMN colour TEXT NOT NULL DEFAULT ''"


def test_upgrading_clears_the_colors_the_old_colour_column_held(tmp_path):
    path = tmp_path / "upgrade.db"
    _before(path, 24, _ADD_COLOUR, "UPDATE lemon_groups SET colour = '#eb7676'")

    with db.connect(path) as conn:
        assert "colour" not in _columns(conn)
        assert groups.store.find(conn, "lemonaid").saved_color == ""


def test_upgrading_adds_the_column_where_there_is_none(tmp_path):
    path = tmp_path / "upgrade.db"
    _before(path, 24)

    with db.connect(path) as conn:
        assert groups.store.find(conn, "lemonaid").saved_color == ""


def test_a_color_saved_in_the_colour_column_survives_the_rename(tmp_path):
    path = tmp_path / "upgrade.db"
    _before(path, 25, _ADD_COLOUR, "UPDATE lemon_groups SET colour = '#112233'")

    with db.connect(path) as conn:
        assert "colour" not in _columns(conn)
        assert groups.store.find(conn, "lemonaid").saved_color == "#112233"


def test_a_color_saved_by_the_merged_migration_25_is_left_alone(tmp_path):
    path = tmp_path / "upgrade.db"
    _before(
        path,
        25,
        "ALTER TABLE lemon_groups ADD COLUMN color TEXT NOT NULL DEFAULT ''",
        "UPDATE lemon_groups SET color = '#112233'",
    )

    with db.connect(path) as conn:
        assert "colour" not in _columns(conn)
        assert groups.store.find(conn, "lemonaid").saved_color == "#112233"
