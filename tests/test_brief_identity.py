"""Stable IDs live in briefs and survive attachment and filename changes."""

import datetime
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
import wordybin

from lemonaid.brief import identity, store
from lemonaid.inbox import db
from lemonaid.inbox.migrations import m009_add_lemon_identities


def _legacy(name: str):
    path = store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: working\n\n## Now\n- Keep this.\n")
    return path


def test_new_brief_stores_a_slugged_id():
    path = store.create("A lemon", datetime.date(2026, 9, 25))

    lemon_id = identity.from_path(path)
    assert identity.valid(lemon_id)
    slug, word = lemon_id.split(".", 1)
    assert slug == "a-lemon"
    assert len(wordybin.decode(word)) == 2
    assert wordybin.encode(wordybin.decode(word)) == word


def test_new_id_uses_filename_slug_without_date_and_trims_at_hyphen(monkeypatch):
    monkeypatch.setattr(store.os, "urandom", lambda size: bytes.fromhex("bdbb"))
    assert (
        store.new_lemon_id(store.briefs_dir() / "2026-09-25-mc-tars-no-mops-leases.md")
        == "mc-tars-no-mops-leases.SkullHen"
    )
    long_name = "2026-09-25-one-two-three-four-five-six-seven-eight-nine-ten-eleven.md"
    slug = store.new_lemon_id(store.briefs_dir() / long_name).split(".", 1)[0]
    assert slug == "one-two-three-four-five-six-seven-eight"


def test_new_brief_regenerates_id_on_registry_collision(monkeypatch):
    values = iter((b"\xbd\xbb", b"\xbd\xbb", b"\0\0"))
    monkeypatch.setattr(store.os, "urandom", lambda size: next(values))
    first = store.create("same slug", datetime.date(2026, 9, 24))
    second = store.create("same slug", datetime.date(2026, 9, 25))
    with db.connect() as conn:
        identity.ensure(conn, first, regenerate_on_collision=True)
        identity.ensure(conn, second, regenerate_on_collision=True)

    assert identity.from_path(first) == "same-slug.SkullHen"
    expected_second = "same-slug." + wordybin.encode(b"\0\0")
    assert identity.from_path(second) == expected_second
    with db.connect() as conn:
        rows = conn.execute("SELECT lemon_id FROM lemon_identities").fetchall()
    assert {row[0] for row in rows} == {identity.from_path(first), identity.from_path(second)}


def test_path_safe_ids_are_opaque_strings():
    canonical = wordybin.encode(bytes.fromhex("dbe69238b4dc49d0"))
    assert canonical == "SwordOwnPanelHadShaftNagFilmyLap"
    for accepted in (
        canonical,
        canonical.lower(),
        wordybin.encode(b"\0" * 16),
        "b0045249ad7b4b9c8dc5bd744f485a18",
        "hand-made.id 123",
        "a" * 255,
    ):
        assert identity.valid(accepted)

    for invalid in (
        canonical + "/outside",
        "../escape",
        "",
        ".hidden",
        "a" * 256,
        "é" * 128,
        "bad\\name",
        "bad\x00name",
        "bad\nname",
    ):
        assert not identity.valid(invalid)


def test_brief_id_header_drops_trailing_whitespace():
    assert identity.read("# Lemon\n\nLemon-ID: hand-made.id 123  \n") == "hand-made.id 123"


def test_legacy_brief_is_backfilled_once_without_losing_its_text():
    path = _legacy("old")
    before = path.read_text()

    with db.connect() as conn:
        first = identity.ensure(conn, path)
        second = identity.ensure(conn, path)
        [row] = conn.execute("SELECT path, lemon_id FROM lemon_identities").fetchall()

    assert first == second == row["lemon_id"]
    assert row["path"] == str(path.resolve())
    assert path.read_text().replace(f"\nLemon-ID: {first}\n", "") == before


def test_concurrent_backfill_assigns_one_id():
    path = _legacy("shared")
    with db.connect():
        pass

    def claim() -> str:
        with db.connect() as conn:
            return identity.ensure(conn, path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(lambda _: claim(), range(2))

    assert first == second == identity.from_path(path)


def test_v8_attachment_can_be_backfilled_after_schema_migration(tmp_path):
    path = _legacy("old-attachment")
    conn = sqlite3.connect(tmp_path / "v8.db")
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "CREATE TABLE session_briefs (channel TEXT PRIMARY KEY, path TEXT NOT NULL, attached_at REAL NOT NULL)"
        )
        conn.execute(
            "INSERT INTO session_briefs (channel, path, attached_at) VALUES (?, ?, ?)",
            ("claude:old", str(path), 1),
        )
        m009_add_lemon_identities.migrate(conn)
        conn.commit()

        lemon_id = identity.ensure(conn, path)

        assert conn.execute("SELECT channel FROM session_briefs").fetchone()[0] == "claude:old"
        assert conn.execute("SELECT lemon_id FROM lemon_identities").fetchone()[0] == lemon_id
        assert identity.from_path(path) == lemon_id
    finally:
        conn.close()


def test_id_survives_a_brief_rename_and_moves_its_registry_entry():
    original = _legacy("original")
    with db.connect() as conn:
        lemon_id = identity.ensure(conn, original)

    renamed = original.rename(original.with_name("renamed.md"))
    with db.connect() as conn:
        assert identity.ensure(conn, renamed) == lemon_id
        [row] = conn.execute("SELECT path FROM lemon_identities").fetchall()

    assert row["path"] == str(renamed.resolve())


def test_copying_a_brief_does_not_duplicate_a_lemon():
    first = _legacy("first")
    with db.connect() as conn:
        identity.ensure(conn, first)

    second = first.with_name("second.md")
    shutil.copyfile(first, second)
    with db.connect() as conn:
        with pytest.raises(ValueError, match="already belongs"):
            identity.ensure(conn, second)
        assert conn.execute("SELECT COUNT(*) FROM lemon_identities").fetchone()[0] == 1


def test_invalid_id_is_rejected_without_replacing_it():
    path = _legacy("bad")
    path.write_text(
        path.read_text().replace("Status: working", "Lemon-ID: ../escape\n\nStatus: working")
    )
    with db.connect() as conn:
        with pytest.raises(ValueError, match="invalid"):
            identity.ensure(conn, path)
        assert conn.execute("SELECT COUNT(*) FROM lemon_identities").fetchone()[0] == 0

    assert "Lemon-ID: ../escape" in path.read_text()


def test_old_hex_id_in_brief_is_kept():
    path = _legacy("old-hex")
    old_id = "b0045249ad7b4b9c8dc5bd744f485a18"
    path.write_text(
        path.read_text().replace("Status: working", f"Lemon-ID: {old_id}\n\nStatus: working")
    )

    with db.connect() as conn:
        assert identity.ensure(conn, path) == old_id
        assert conn.execute("SELECT lemon_id FROM lemon_identities").fetchone()[0] == old_id

    assert identity.from_path(path) == old_id


def test_body_examples_do_not_count_as_identity_lines():
    path = _legacy("examples")
    path.write_text(
        path.read_text() + "\nLemon-ID: example-in-body\n    Lemon-ID: example-in-code\n"
    )

    with db.connect() as conn:
        lemon_id = identity.ensure(conn, path)

    assert identity.from_path(path) == lemon_id
    assert "Lemon-ID: example-in-body" in path.read_text()


def test_outside_nested_and_symlink_briefs_are_rejected(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n")
    nested = store.briefs_dir() / "nested" / "brief.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("# Nested\n")
    link = store.briefs_dir() / "link.md"
    link.symlink_to(outside)

    with db.connect() as conn:
        for path in (outside, nested, link):
            with pytest.raises(ValueError):
                identity.ensure(conn, path)
