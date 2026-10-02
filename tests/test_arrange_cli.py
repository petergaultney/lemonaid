"""`lemonaid inbox arrange check` tries an arranger against the live inbox and reports on it."""

import json
import sys

import pytest

import lemonaid.cli
from tests.test_arrange_tui import _serve, _sessions


def _check(monkeypatch, command: str) -> int:
    monkeypatch.setattr(
        sys, "argv", ["lemonaid", "inbox", "arrange", "check", "--command", command]
    )
    with pytest.raises(SystemExit) as exit:
        lemonaid.cli.main()
    return exit.value.code


def test_check_lists_the_arranged_rows_and_its_problems(monkeypatch, tmp_path, capsys):
    a, b, c = _sessions("a", "b", "c")
    command = _serve(tmp_path, f"def arrange(snapshot):\n    return {{'rows': [99, {a}]}}\n")

    code = _check(monkeypatch, command)

    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith(f"3 rows:\n  {a:>6}    a\n  {c:>6}    c\n  {b:>6}    b\n")
    assert "problem: rows: no row 99, ignored" in out


def test_check_passes_an_arranger_with_nothing_to_correct(monkeypatch, tmp_path, capsys):
    _sessions("a", "b")
    command = _serve(
        tmp_path,
        "from lemonaid.inbox.arrange import answer\n"
        "def arrange(snapshot):\n    return answer.default(snapshot)\n",
    )

    assert _check(monkeypatch, command) == 0
    assert "problem" not in capsys.readouterr().out


def test_check_shows_a_failing_arranger_its_traceback(monkeypatch, tmp_path, capsys):
    _sessions("a")
    command = _serve(tmp_path, "def arrange(snapshot):\n    return snapshot['nope']\n")

    assert _check(monkeypatch, command) == "unusable answer: arranger says: KeyError: 'nope'"
    assert "Traceback" in capsys.readouterr().err


def test_snapshot_prints_each_row_with_the_inbox_own_answer(monkeypatch, tmp_path, capsys):
    a, b = _sessions("a", "b")
    monkeypatch.setattr(sys, "argv", ["lemonaid", "inbox", "arrange", "snapshot", "--width", "50"])

    lemonaid.cli.main()

    snapshot = json.loads(capsys.readouterr().out)
    assert (snapshot["version"], snapshot["layout"], snapshot["width"]) == (1, "sidebar", 50)
    assert [(r["id"], r["name"], r["default"]) for r in snapshot["rows"]] == [
        (b, "b", {"position": 0, "band": "read", "folded": False}),
        (a, "a", {"position": 1, "band": "read", "folded": False}),
    ]
