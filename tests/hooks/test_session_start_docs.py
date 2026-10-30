import io
import json
import os
from pathlib import Path

import pytest

from lemonaid.hooks import session_start


def _start(monkeypatch, capsys, source: str, harness: str = "codex") -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"source": source})))
    session_start.handle(harness)
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""


@pytest.fixture
def context_doc(tmp_path):
    (tmp_path / "rules.md").write_text("RULES")
    (tmp_path / "root.md").write_text("ROOT\n@rules.md\n")
    Path(os.environ["LEMONAID_CONFIG"]).write_text(
        f'[codex]\ncontext_doc = "{tmp_path / "root.md"}"\n'
    )


@pytest.mark.usefixtures("context_doc")
@pytest.mark.parametrize("source", ["startup", "clear", "compact"])
def test_a_fresh_history_gets_the_doc_and_its_imports(monkeypatch, capsys, source):
    text = _start(monkeypatch, capsys, source)

    assert "ROOT" in text and "RULES" in text


@pytest.mark.usefixtures("context_doc")
@pytest.mark.parametrize("source", ["resume", "fork"])
def test_a_history_that_already_holds_it_gets_nothing(monkeypatch, capsys, source):
    assert _start(monkeypatch, capsys, source) == ""


@pytest.mark.usefixtures("context_doc")
def test_claude_loads_its_own_docs(monkeypatch, capsys):
    assert _start(monkeypatch, capsys, "startup", harness="claude") == ""


def test_no_context_doc_configured_injects_nothing(monkeypatch, capsys):
    assert _start(monkeypatch, capsys, "startup") == ""


def test_a_missing_context_doc_does_not_break_the_start(monkeypatch, capsys, tmp_path):
    Path(os.environ["LEMONAID_CONFIG"]).write_text(
        f'[codex]\ncontext_doc = "{tmp_path / "gone.md"}"\n'
    )

    assert _start(monkeypatch, capsys, "startup") == ""


def test_a_broken_config_keeps_stdout_one_json_value(monkeypatch, capsys):
    Path(os.environ["LEMONAID_CONFIG"]).write_text("[broken\n")
    monkeypatch.setattr(session_start, "context", lambda data, harness: "BRIEF")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"source": "startup"})))

    session_start.handle("codex")

    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["additionalContext"] == "BRIEF"
