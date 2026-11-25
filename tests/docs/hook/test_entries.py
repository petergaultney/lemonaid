"""The docs hook end to end for a classic lemon: what it logs, and doesn't deliver, for
each event, from docs under `[docs] roots`."""

import io
import json
from pathlib import Path

import pytest

from lemonaid.config import load_config
from lemonaid.docs import deliveries, hook, index, lemons, paths, start, window

from ..shared import configure, doc

_SESSION = "0f0e0d0c-1111-2222-3333-444455556666"


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "docs"
    doc(root, "packages/core.md", {"package-for": [{}]})
    doc(root, "packages/python.md", {"package-for": [{"file": "pyproject.toml"}]})
    doc(
        root,
        "voice.md",
        {"package": "core", "load-when": [{"command": r"^git commit\b"}], "reminder": "Plainly."},
        "Write plainly.\n",
    )
    doc(
        root,
        "prs.md",
        {
            "load-when": [
                {"command": r"^gh pr create\b", "section": "Drafts", "before": True},
                {"command": r"^gh pr (view|checks)\b"},
            ],
            "reminder": "Open PRs as drafts.",
        },
        "# PRs\n\n## Drafts\n\nOpen as a draft.\n\n## Merging\n\nNot you.\n",
    )
    doc(root, "notes.md", {"load-when": [{"create": "notes/*.md"}, {"prompt": "(?i)daily note"}]})
    configure([root])
    index.build([root], paths.index())  # as another session's start would have
    return root


def _run(event: str, harness: str = "claude", **fields) -> list[dict]:
    data = {"session_id": _SESSION, "hook_event_name": event, "cwd": "/tmp", **fields}
    return hook.outcome(data, harness, load_config()).entries


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


@pytest.mark.usefixtures("root")
def test_a_session_start_logs_its_window_and_its_packages_docs(tmp_path):
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "pyproject.toml").touch()

    started, delivered = _run("SessionStart", source="startup", cwd=str(tmp_path / "repo"))

    assert started["kind"] == "window"
    assert started["packages"] == ["core", "python"]
    assert started["shadow"] is True and started["mode"] == "classic"
    assert delivered["doc"].endswith("voice.md")
    assert (delivered["package"], delivered["delivery"], delivered["shadow"]) == (
        "core",
        "full",
        True,
    )
    assert delivered["chars"] == len(start.block(Path(delivered["doc"]), "Write plainly."))


@pytest.mark.usefixtures("root")
def test_a_before_trigger_would_refuse_once_then_its_reminder_follows_much_later():
    _run("SessionStart", source="startup")

    (first,) = _run("PreToolUse", **_bash("cd app && gh pr create --fill"))
    assert (first["delivery"], first["section"], first["chars"]) == (
        "refuse",
        "Drafts",
        len(start.block(Path(first["doc"]), "## Drafts\n\nOpen as a draft.", "Drafts")),
    )
    assert first["trigger"] == r"command ^gh pr create\b"
    assert _run("PreToolUse", **_bash("gh pr create --draft")) == []

    for _ in range(window.REMIND_AFTER):
        _run("PreToolUse", **_bash("ls"))
    (again,) = _run("PreToolUse", **_bash("gh pr create --draft"))
    assert again["delivery"] == "reminder"
    assert again["chars"] == len(f"Reminder from {again['doc']}: Open PRs as drafts.")


@pytest.mark.usefixtures("root")
def test_a_package_s_doc_gives_its_reminder_at_its_trigger():
    _run("SessionStart", source="startup")

    (entry,) = _run("PreToolUse", **_bash("git commit -m x"))

    assert entry["delivery"] == "reminder"
    assert entry["chars"] == len(f"Reminder from {entry['doc']}: Plainly.")
    assert _run("PreToolUse", **_bash("git commit -m y")) == []


@pytest.mark.usefixtures("root")
def test_a_resume_logs_the_packages_its_window_was_given(monkeypatch, tmp_path):
    doc(tmp_path / "docs", "packages/grove.md", {"package-for": [{"brief": True}]})
    index.build([tmp_path / "docs"], paths.index())
    (started, *_) = _run("SessionStart", source="startup")
    monkeypatch.setattr(lemons, "attached_brief", lambda harness, session: "# A brief\n")

    (resumed,) = _run("SessionStart", source="resume")

    assert started["packages"] == resumed["packages"] == ["core"]


@pytest.mark.usefixtures("root")
def test_compaction_starts_a_window_that_needs_the_doc_again():
    _run("SessionStart", source="startup")
    assert _run("PreToolUse", **_bash("gh pr view 3"))
    _run("SessionStart", source="resume")
    assert _run("PreToolUse", **_bash("gh pr view 3")) == []

    _run("SessionStart", source="compact")

    (entry,) = _run("PreToolUse", **_bash("gh pr view 3"))
    assert (entry["window"], entry["delivery"], entry["section"]) == (2, "full", "")


@pytest.mark.usefixtures("root")
def test_creates_in_each_harness(tmp_path):
    _run("SessionStart", source="startup")
    _run("SessionStart", harness="codex", source="startup")
    patch = "*** Begin Patch\n*** Add File: notes/today.md\n+hi\n*** End Patch\n"
    codex = {"tool_name": "apply_patch", "tool_input": {"command": patch}, "cwd": str(tmp_path)}
    write = {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "notes/a.md")}}

    (from_patch,) = _run("PreToolUse", harness="codex", **codex)
    assert _run("PreToolUse", **write) == []
    (from_write,) = _run("PostToolUse", **write, tool_response={"type": "create"})

    assert from_patch["trigger"] == from_write["trigger"] == "create notes/*.md"


@pytest.mark.usefixtures("root")
def test_a_prompt_trigger():
    _run("SessionStart", source="startup")
    (entry,) = _run("UserPromptSubmit", prompt="Add this to my daily note")

    assert entry["doc"].endswith("notes.md")


@pytest.mark.usefixtures("root")
def test_a_subagent_s_calls_are_skipped():
    assert _run("PreToolUse", agent_id="sub-1", **_bash("gh pr view 3")) == []


def test_without_roots_the_hook_logs_nothing(monkeypatch):
    stdin = {"session_id": _SESSION, "hook_event_name": "PreToolUse", **_bash("gh pr view 3")}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin)))

    hook.handle("claude")

    assert list(deliveries.read()) == []


@pytest.mark.usefixtures("root")
def test_the_hook_appends_to_the_log(monkeypatch):
    stdin = {"session_id": _SESSION, "hook_event_name": "PreToolUse", **_bash("gh pr view 3")}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin)))

    hook.handle("codex")

    entry, *_ = deliveries.read()
    assert (entry["harness"], entry["session"], entry["doc"][-6:]) == ("codex", _SESSION, "prs.md")
