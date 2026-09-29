import argparse
import json

import pytest

from lemonaid.home import cli, layout

from .shared import old_home_with_work


def _run(capsys, *argv: str) -> tuple[dict, int]:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["home", "migrate", *argv, "--json"])
    code = 0
    try:
        args.func(args)
    except SystemExit as exit:
        code = exit.code or 0
    return json.loads(capsys.readouterr().out), code


def test_a_dry_run_counts_what_would_move_and_changes_nothing(capsys):
    old_home_with_work()

    planned, code = _run(capsys, "--dry-run")

    assert code == 0
    assert planned["blockers"] == []
    assert planned["files"] == 4
    assert planned["db_rows"] == {"session_briefs": 1, "pending_briefs": 1, "lemon_identities": 1}
    assert not layout.lemons_dir().exists()


def test_migrate_then_rollback_from_the_command_line(capsys):
    old_home_with_work()

    migrated, code = _run(capsys)
    assert (migrated["done"], code) == (True, 0)

    rolled_back, code = _run(capsys, "--rollback")
    assert (rolled_back["done"], code) == (True, 0)


def test_a_single_folder_override_refuses_the_migration(capsys, monkeypatch, tmp_path):
    old_home_with_work()
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(tmp_path / "pinned"))
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["home", "migrate"])

    with pytest.raises(SystemExit):
        args.func(args)

    assert "LEMONAID_BRIEFS_DIR pins" in capsys.readouterr().err
    assert layout.legacy_dir().exists()
