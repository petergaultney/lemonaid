"""`lemonaid rules replay`: what patterns would have matched in past transcripts."""

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

import lemonaid.cli
from lemonaid.rules import end_of_turn
from tests.rules import shared


@pytest.fixture
def claude_home(monkeypatch, tmp_path) -> Path:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    return tmp_path / "claude"


def _transcript(home: Path, *said: str) -> Path:
    path = home / "projects" / "-work-repo" / "s1.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    at = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)).isoformat()
    path.write_text(
        "".join(
            json.dumps(entry) + "\n"
            for number, text in enumerate(said)
            for entry in (
                {
                    "type": "assistant",
                    "timestamp": at,
                    "cwd": "/work/repo",
                    "message": {"id": f"m{number}", "content": [{"type": "text", "text": text}]},
                },
                {"type": "user", "message": {"content": "ok"}},
            )
        )
    )
    return path


def _run(monkeypatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["lemonaid", "rules", "replay", *args])
    lemonaid.cli.main()


def test_replay_lists_each_hit_and_counts_them(monkeypatch, tmp_path, capsys, claude_home):
    transcript = _transcript(
        claude_home, "Done. Ready to merge?", "Should I start a reviewer?", "Fine."
    )
    source = shared.write(tmp_path / "p", shared.MERGE_ASK, shared.REVIEWER_ASK)

    _run(monkeypatch, "--file", str(source))

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("merge-ask  ")
    assert lines[0].endswith("  claude  /work/repo")
    assert lines[1:3] == ["  Done. **Ready to merge?**", f"  {transcript}"]
    assert lines[-3].startswith("3 end-of-turn messages since ")
    assert lines[-2:] == ["  merge-ask: 1", "  reviewer-ask: 1"]


def test_replay_runs_only_the_patterns_named(monkeypatch, tmp_path, capsys, claude_home):
    _transcript(claude_home, "Ready to merge?", "Should I start a reviewer?")
    source = shared.write(tmp_path / "p", shared.MERGE_ASK, shared.REVIEWER_ASK)

    _run(monkeypatch, "reviewer-ask", "--file", str(source))

    assert capsys.readouterr().out.splitlines()[-1] == "  reviewer-ask: 1"


def test_replay_needs_no_promote_and_skips_patterns_that_don_t_parse(
    monkeypatch, tmp_path, capsys, claude_home
):
    _transcript(claude_home, "Ready to merge?")
    source = shared.write(tmp_path / "p", shared.MERGE_ASK, {**shared.REVIEWER_ASK, "oops": 1})

    _run(monkeypatch, "--file", str(source))

    captured = capsys.readouterr()
    assert "reviewer-ask: unknown key 'oops'" in captured.err
    assert captured.out.splitlines()[-1] == "  merge-ask: 1"


def test_replay_refuses_a_regex_that_could_hang(monkeypatch, tmp_path, claude_home):
    source = shared.write(tmp_path / "p", {**shared.MERGE_ASK, "regex": r"(\w+\s?)+merge"})

    with pytest.raises(SystemExit) as exited:
        _run(monkeypatch, "--file", str(source))

    assert "nests one quantifier" in str(exited.value.code)


def test_replay_refuses_an_unknown_id_or_duration(monkeypatch, tmp_path, claude_home):
    source = shared.write(tmp_path / "p", shared.MERGE_ASK)

    with pytest.raises(SystemExit) as unknown:
        _run(monkeypatch, "nope", "--file", str(source))
    with pytest.raises(SystemExit) as duration:
        _run(monkeypatch, "--since", "fortnight", "--file", str(source))

    assert str(unknown.value.code).endswith("has no pattern nope")
    assert "--since must be a duration" in str(duration.value.code)


def test_a_pattern_that_runs_out_of_time_is_named_and_not_run_again(
    monkeypatch, tmp_path, capsys, claude_home
):
    monkeypatch.setattr(end_of_turn, "_SEARCH_SECONDS", 0.05)
    transcript = _transcript(claude_home, "a" * 10000 + "!", "aa", "Ready to merge?")
    slow = {**shared.REVIEWER_ASK, "regex": r"(a|aa)+$", "match": ["aa"]}
    source = shared.write(tmp_path / "p", slow, shared.MERGE_ASK)

    _run(monkeypatch, "--file", str(source))

    lines = capsys.readouterr().out.splitlines()
    assert lines[-3:-1] == ["  reviewer-ask: 0", "  merge-ask: 1"]
    assert lines[-1].startswith("reviewer-ask ran out of time on the turn at ")
    assert lines[-1].endswith(
        f"in {transcript}, which the hook would skip too, and wasn't run after it"
    )
