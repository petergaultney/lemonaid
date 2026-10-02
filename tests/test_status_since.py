from pathlib import Path

from lemonaid.inbox import db, status_since


def test_a_status_keeps_its_start_through_later_edits(tmp_path: Path) -> None:
    brief = tmp_path / "brief.md"
    with db.connect(tmp_path / "test.db") as conn:
        assert status_since.observe(conn, {brief: ("waiting", 100.0)}) == {brief: 100.0}
        assert status_since.observe(conn, {brief: ("waiting", 900.0)}) == {brief: 100.0}


def test_a_new_status_starts_again_from_the_edit_that_set_it(tmp_path: Path) -> None:
    brief = tmp_path / "brief.md"
    with db.connect(tmp_path / "test.db") as conn:
        status_since.observe(conn, {brief: ("waiting", 100.0)})
        status_since.observe(conn, {brief: ("working", 200.0)})
        assert status_since.observe(conn, {brief: ("waiting", 300.0)}) == {brief: 300.0}


def test_the_record_outlives_the_connection(tmp_path: Path) -> None:
    brief, other = tmp_path / "brief.md", tmp_path / "other.md"
    with db.connect(tmp_path / "test.db") as conn:
        status_since.observe(conn, {brief: ("waiting", 100.0)})

    with db.connect(tmp_path / "test.db") as conn:
        assert status_since.observe(conn, {brief: ("waiting", 500.0), other: ("done", 50.0)}) == {
            brief: 100.0,
            other: 50.0,
        }
        assert status_since.observe(conn, {}) == {}
