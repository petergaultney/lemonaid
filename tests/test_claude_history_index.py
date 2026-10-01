"""Sessions are found in history.jsonl by reading each appended line once."""

import json
import os

from lemonaid.claude import projects


def _append(path, *entries: dict) -> None:
    with open(path, "a") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _history(monkeypatch, tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text("")
    monkeypatch.setattr(projects, "_HISTORY_PATH", path)
    monkeypatch.setattr(projects, "_history", projects._HistoryIndex())
    return path


def test_a_session_appended_later_is_found(monkeypatch, tmp_path):
    path = _history(monkeypatch, tmp_path)
    _append(path, {"sessionId": "a", "project": "/one"})
    assert projects._find_in_history("b") is None

    _append(path, {"sessionId": "b", "project": "/two"})

    assert projects._find_in_history("b") == "/two"
    assert projects._find_in_history("a") == "/one"


def test_the_latest_project_for_a_session_wins(monkeypatch, tmp_path):
    path = _history(monkeypatch, tmp_path)
    _append(path, {"sessionId": "a", "project": "/one"}, {"sessionId": "a", "project": "/two"})

    assert projects._find_in_history("a") == "/two"


def test_a_line_still_being_written_is_read_once_it_is_finished(monkeypatch, tmp_path):
    path = _history(monkeypatch, tmp_path)
    with open(path, "a") as f:
        f.write('{"sessionId": "a", "proj')
    assert projects._find_in_history("a") is None

    with open(path, "a") as f:
        f.write('ect": "/one"}\n')

    assert projects._find_in_history("a") == "/one"


def test_a_replaced_file_is_read_from_the_start(monkeypatch, tmp_path):
    path = _history(monkeypatch, tmp_path)
    _append(path, {"sessionId": "a", "project": "/one"})
    assert projects._find_in_history("a") == "/one"

    replacement = tmp_path / "new.jsonl"
    _append(replacement, {"sessionId": "b", "project": "/two"})
    os.replace(replacement, path)

    assert projects._find_in_history("a") is None
    assert projects._find_in_history("b") == "/two"


def test_a_miss_does_not_reread_the_file(monkeypatch, tmp_path):
    path = _history(monkeypatch, tmp_path)
    _append(path, {"sessionId": "a", "project": "/one"})
    projects._find_in_history("missing")
    reads: list[int] = []
    real = projects.json.loads
    monkeypatch.setattr(projects.json, "loads", lambda line: (reads.append(1), real(line))[1])

    for _ in range(5):
        assert projects._find_in_history("missing") is None

    assert reads == []
