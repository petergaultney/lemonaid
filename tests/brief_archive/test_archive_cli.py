import argparse
import time

from lemonaid.brief import archive, archive_cli
from lemonaid.inbox import db

from .shared import brief, session


def _run(*argv: str, code: int = 0) -> None:
    parser = argparse.ArgumentParser()
    archive_cli.add_parsers(parser.add_subparsers())
    args = parser.parse_args(list(argv))
    try:
        args.func(args)
    except SystemExit as stop:
        assert (stop.code or 0) == code
        return

    assert code == 0


def test_a_dry_run_lists_idle_briefs_and_moves_nothing(capsys):
    old, _ = brief("old")
    brief("fresh", at=time.time())

    _run("archive", "--idle-days", "14", "--dry-run")

    assert "old.md" in capsys.readouterr().out
    assert old.exists()


def test_a_sweep_moves_only_the_idle_briefs():
    old, _ = brief("old")
    fresh, _ = brief("fresh", at=time.time())

    _run("archive", "--idle-days", "14")

    assert not old.exists() and fresh.exists()
    assert list(archive.attic_dir().glob("*/old.md"))


def test_a_sweep_with_another_database_moves_no_brief_it_never_recorded(monkeypatch, tmp_path):
    held, _ = brief("lead")
    session(held, "claude:lead", live=True)
    monkeypatch.setattr(db, "get_db_path", lambda: tmp_path / "sandbox.db")

    _run("archive", "--idle-days", "14")

    assert held.exists()
    assert not list(archive.attic_dir().rglob("*.md"))


def test_a_sweep_finding_more_idle_briefs_than_its_limit_moves_none_and_says_so():
    briefs = [brief(name)[0] for name in ("one", "two", "three")]

    _run("archive", "--idle-days", "14", "--max", "2", code=1)

    assert all(path.exists() for path in briefs)
    with db.connect() as conn:
        said = db.get_by_channel(conn, "lemonaid:brief-sweep")
    assert said is not None
    assert said.message.startswith("The brief sweep found 3 briefs unused for 14+ days")


def test_a_sweep_within_its_limit_moves_the_idle_briefs():
    old, _ = brief("old")

    _run("archive", "--idle-days", "14", "--max", "1")

    assert not old.exists()


def test_one_brief_is_archived_by_its_lemon_id_and_revived_by_it():
    path, lemon_id = brief("named", at=time.time())

    _run("archive", lemon_id)
    assert not path.exists()

    _run("revive", lemon_id)
    assert path.exists()
