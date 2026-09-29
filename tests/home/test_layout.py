import argparse
import contextlib
import json

from lemonaid.brief import status, store, write_cli
from lemonaid.home import layout
from lemonaid.messages import store as message_store


def test_the_old_home_stays_active_until_cutover():
    layout.legacy_dir().mkdir()
    (layout.lemons_dir() / "brief").mkdir(parents=True)

    assert store.briefs_dir() == layout.legacy_dir()
    assert message_store.inbox_root() == layout.legacy_dir() / "inbox"

    (layout.lemons_dir() / layout.CUTOVER).write_text("x\n")

    assert store.briefs_dir() == layout.lemons_dir() / "brief"
    assert message_store.inbox_root() == layout.lemons_dir() / "inbox"


def test_a_machine_that_never_had_the_old_home_uses_the_new_one():
    assert store.briefs_dir() == layout.lemons_dir() / "brief"


def test_a_migration_in_progress_neither_flips_the_home_nor_allows_brief_commands(capsys):
    layout.lemons_dir().mkdir()
    (layout.lemons_dir() / layout.MIGRATING).write_text("x\n")

    assert not layout.cut_over()
    assert "migration is in progress" in store.outside_error(layout.legacy_dir() / "a.md")
    parser = argparse.ArgumentParser()
    write_cli.add_parsers(parser.add_subparsers())
    args = parser.parse_args(["new", "--channel", "claude:x", "--json", "title"])
    with contextlib.suppress(SystemExit):
        args.func(args)
    assert "migration is in progress" in json.loads(capsys.readouterr().out)["error"]


def test_a_brief_is_not_shown_while_a_migration_is_in_progress(tmp_path):
    layout.lemons_dir().mkdir()
    (layout.lemons_dir() / layout.MIGRATING).write_text("x\n")

    shown = status.find([tmp_path / "brief.md"], [], None, [], 0)

    assert "migration is in progress" in shown
