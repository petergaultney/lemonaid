"""`lemonaid rules check [--promote]`."""

import json
import os
import sys
from pathlib import Path

import pytest

import lemonaid.cli
from lemonaid.rules import report, snapshot
from tests.rules import shared


def _run(monkeypatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["lemonaid", "rules", "check", *args])
    lemonaid.cli.main()


def test_check_reads_the_configured_file_and_names_each_pattern_s_mode(
    monkeypatch, tmp_path, capsys
):
    source = shared.write(
        tmp_path, shared.MERGE_ASK, {**shared.REVIEWER_ASK, "mode": "tell", "say": "Do it."}
    )
    shared.configure(Path(os.environ["LEMONAID_CONFIG"]), source)

    _run(monkeypatch)

    assert capsys.readouterr().out == (
        f"{source}: every check passes for merge-ask (report), reviewer-ask (tell)\n"
    )
    assert not snapshot.path().exists()


def test_promote_writes_the_snapshot(monkeypatch, tmp_path, capsys):
    source = shared.write(tmp_path, shared.MERGE_ASK)
    shared.configure(Path(os.environ["LEMONAID_CONFIG"]), source)

    _run(monkeypatch, "--promote")

    assert capsys.readouterr().out.splitlines()[-1] == f"Promoted to {snapshot.path()}"
    assert json.loads(snapshot.path().read_text())["source"] == str(source.resolve())


def test_promoting_a_file_the_config_doesn_t_name_says_so(monkeypatch, tmp_path, capsys):
    source = shared.write(tmp_path, shared.MERGE_ASK)

    _run(monkeypatch, "--file", str(source), "--promote")

    assert "won't read these patterns" in capsys.readouterr().out
    assert snapshot.path().exists()


def test_a_problem_exits_1_and_leaves_the_snapshot_alone(monkeypatch, tmp_path):
    good = shared.write(tmp_path / "good", shared.MERGE_ASK)
    _run(monkeypatch, "--file", str(good), "--promote")
    bad = shared.write(tmp_path / "bad", {**shared.MERGE_ASK, "match": ["Merge it?"]})

    with pytest.raises(SystemExit) as exited:
        _run(monkeypatch, "--file", str(bad), "--promote")

    assert exited.value.code == (
        f"{bad}:\n- merge-ask: does not match its match example 'Merge it?'"
    )
    assert json.loads(snapshot.path().read_text())["source"] == str(good.resolve())


def test_without_a_configured_or_given_file_check_says_how_to_name_one(monkeypatch):
    with pytest.raises(SystemExit) as exited:
        _run(monkeypatch)

    assert "set [rules] patterns" in str(exited.value.code)


def test_a_rule_promoted_from_a_relative_file_is_found_from_any_directory(
    monkeypatch, tmp_path, capsys
):
    source = shared.write(tmp_path / "rules", {**shared.MERGE_ASK, "mode": "tell"})
    monkeypatch.chdir(source.parent)
    _run(monkeypatch, "--file", "patterns.toml", "--promote")
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")
    (tmp_path / "elsewhere" / "rules.md").write_text(
        "- **A PR ready to merge is someone else's rule."
    )

    [pattern] = snapshot.load(source)

    assert pattern.rule_file == source.parent / "rules.md"
    assert "> - **A PR ready to merge gets the merge Status.**" in report.telling(pattern)
