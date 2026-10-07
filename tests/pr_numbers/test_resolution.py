import pytest

from lemonaid.config import PlaceRoot, PlacesConfig
from lemonaid.inbox import db
from lemonaid.inbox.tui import pr_numbers

from .shared import table


@pytest.mark.parametrize("branch_number", [pr_numbers.PR("99"), None])
def test_branch_precedence_and_single_table_fallback(tmp_path, branch_number):
    root = PlaceRoot(tmp_path, open_prs="lookup")
    places = PlacesConfig(roots=[root])
    cache = pr_numbers.Cache()
    cache.store(root, {"topic": branch_number} if branch_number else {}, 0)
    with db.connect() as conn:
        for name in ("parent", "single", "many", "empty", "author", "reviewer", "other", "invalid"):
            db.add(
                conn,
                f"codex:{name}",
                "message",
                name,
                {"cwd": str(tmp_path / name), "git_branch": "topic"},
                status="read",
            )
            path = tmp_path / f"{name}.md"
            path.write_text(
                table(12)
                if name in {"single", "parent"}
                else table(12, 13)
                if name == "many"
                else table()
                if name == "empty"
                else "## Now\n### PRs\nbroken"
                if name == "invalid"
                else "## Now\n"
            )
            pr_numbers.attached.attach(conn, f"codex:{name}", path)
            conn.execute("INSERT INTO lemon_identities VALUES (?, ?)", (str(path), f"{name}.Id"))
        conn.execute("INSERT INTO lemon_parents VALUES (?, ?, ?)", ("child.Id", "parent.Id", 0))
        conn.commit()
        numbers = pr_numbers.rows(conn, db.get_active(conn), places, cache)
    assert numbers == (
        {
            f"codex:{name}": pr_numbers.PR("99")
            for name in (
                "parent",
                "single",
                "many",
                "empty",
                "author",
                "reviewer",
                "other",
                "invalid",
            )
        }
        if branch_number
        else {
            "codex:parent": pr_numbers.PR("12", "https://github.com/owner/repo/pull/12"),
            "codex:single": pr_numbers.PR("12", "https://github.com/owner/repo/pull/12"),
        }
    )


def test_nested_root_and_missing_metadata(tmp_path):
    outer = PlaceRoot(tmp_path, open_prs="outer")
    inner = PlaceRoot(tmp_path / "nested", open_prs="inner")
    cache = pr_numbers.Cache()
    cache.store(outer, {"topic": pr_numbers.PR("1")}, 0)
    cache.store(inner, {"topic": pr_numbers.PR("2")}, 0)
    with db.connect() as conn:
        for name, meta in (
            ("nested", {"cwd": str(inner.path), "git_branch": "topic"}),
            ("no-cwd", {"git_branch": "topic"}),
            ("no-branch", {"cwd": str(tmp_path)}),
            ("outside", {"cwd": "/elsewhere", "git_branch": "topic"}),
        ):
            db.add(conn, f"codex:{name}", "message", name, meta, status="read")
        assert pr_numbers.rows(
            conn, db.get_active(conn), PlacesConfig(roots=[outer, inner]), cache
        ) == {"codex:nested": pr_numbers.PR("2")}


def test_fallback_updates_when_branch_map_changes(tmp_path):
    root = PlaceRoot(tmp_path, open_prs="lookup")
    places = PlacesConfig(roots=[root])
    cache = pr_numbers.Cache()
    with db.connect() as conn:
        path = tmp_path / "brief.md"
        path.write_text(table(12))
        db.add(
            conn,
            "codex:task",
            "message",
            "task",
            {"cwd": str(tmp_path), "git_branch": "topic"},
            status="read",
        )
        pr_numbers.attached.attach(conn, "codex:task", path)
        notifications = db.get_active(conn)
        cache.store(root, {"topic": pr_numbers.PR("99")}, 0)
        assert pr_numbers.rows(conn, notifications, places, cache) == {
            "codex:task": pr_numbers.PR("99")
        }
        cache.store(root, {}, 180)
        assert pr_numbers.rows(conn, notifications, places, cache) == {
            "codex:task": pr_numbers.PR("12", "https://github.com/owner/repo/pull/12")
        }
        path.write_text(table(12, 13))
        assert pr_numbers.rows(conn, notifications, places, cache) == {}
