"""`brief new --child` names the child from its parent's `Name words:` line, or `--name-words`."""

import argparse
import contextlib
import json

import pytest

from lemonaid.brief import identity, store, write_cli
from lemonaid.inbox import db

_PARENT = "hq.BlessBar"


def _run(capsys, *argv: str) -> dict:
    """The command's JSON result, with its stderr under "stderr"."""
    parser = argparse.ArgumentParser()
    write_cli.add_parsers(parser.add_subparsers())
    args = parser.parse_args(["new", "--child", "--parent", _PARENT, *argv, "--json"])
    with contextlib.suppress(SystemExit):
        args.func(args)

    captured = capsys.readouterr()
    return {**json.loads(captured.out), "stderr": captured.err}


@pytest.fixture(autouse=True)
def parent():
    path = store.briefs_dir() / "2026-09-01-hq.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# hq\n\nLemon-ID: {_PARENT}\nName words: audit check ink review web\n")
    with db.connect() as conn:
        identity.ensure(conn, path)
    return path


def test_children_take_the_parent_s_words_in_order_skipping_held_names(capsys):
    results = [_run(capsys, f"Task {i}") for i in range(3)]

    assert [identity.brief_name(r["lemon_id"]) for r in results] == [
        "AuditInk",
        "AuditWeb",
        "CheckInk",
    ]
    assert "Skipping review on hq.BlessBar's Name words line" in results[0]["stderr"]
    assert "Named AuditInk from the name words" in results[0]["stderr"]


def test_name_words_override_the_parent_s_line(capsys):
    assert _run(capsys, "--name-words", "spark,tea", "One")["lemon_id"].endswith(".SparkTea")


def test_a_malformed_name_word_is_an_error_before_any_brief_is_written(capsys):
    result = _run(capsys, "--name-words", "spark,teas", "One")

    assert "teas is not five or three letters" in result["error"]
    assert not list(store.briefs_dir().glob("*-one.md"))


def test_when_every_pair_is_held_the_child_gets_a_random_name(capsys):
    _run(capsys, "--name-words", "spark,tea", "One")
    second = _run(capsys, "--name-words", "spark,tea", "Two")

    assert not second["lemon_id"].endswith(".SparkTea")
    assert "Every name the name words make is taken" in second["stderr"]
    assert len(identity.brief_name(second["lemon_id"])) == 8


def test_a_name_an_active_lemon_holds_only_as_an_alias_is_skipped(capsys):
    with db.connect() as conn:
        conn.execute("INSERT INTO lemon_aliases VALUES ('hq.SparkTea', ?)", (_PARENT,))
        conn.commit()

    assert _run(capsys, "--name-words", "spark,tea,ink", "One")["lemon_id"].endswith(".SparkInk")
