"""Tests for Claude session-name resolution and name upgrades.

The bug these cover: Claude writes an AI-generated `summary` into
sessions-index.json only after a session has some content, so the first hook
fire legitimately sees only `firstPrompt` (or nothing at all, falling back to a
tmux/cwd placeholder). A later fire must be able to upgrade the stored name.
"""

import json
import tempfile
from pathlib import Path

from lemonaid.claude import notify
from lemonaid.inbox import db

_SESSION = "abc12345-0000-0000-0000-000000000000"


def _write_index(project_dir: Path, entry: dict) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sessions-index.json").write_text(json.dumps({"entries": [entry]}))


def _patch_home(monkeypatch, home: Path) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))


def test_prefers_summary_over_first_prompt(monkeypatch, tmp_path):
    """The AI-generated summary is the name we actually want in the inbox."""
    cwd = "/Users/x/play/lemonaid"
    _patch_home(monkeypatch, tmp_path)
    _write_index(
        tmp_path / ".claude" / "projects" / "-Users-x-play-lemonaid",
        {
            "sessionId": _SESSION,
            "firstPrompt": "please go fix the thing that is broken somehow",
            "summary": "Fix broken notification hook",
        },
    )

    assert notify.get_session_name(_SESSION, cwd) == "Fix broken notification hook"


def test_custom_title_beats_summary(monkeypatch, tmp_path):
    cwd = "/Users/x/play/lemonaid"
    _patch_home(monkeypatch, tmp_path)
    _write_index(
        tmp_path / ".claude" / "projects" / "-Users-x-play-lemonaid",
        {
            "sessionId": _SESSION,
            "customTitle": "my-name",
            "summary": "Fix broken notification hook",
            "firstPrompt": "whatever",
        },
    )

    assert notify.get_session_name(_SESSION, cwd) == "my-name"


def test_falls_back_to_truncated_first_prompt(monkeypatch, tmp_path):
    """Before a summary exists, the first prompt is the best available name."""
    cwd = "/Users/x/play/lemonaid"
    _patch_home(monkeypatch, tmp_path)
    _write_index(
        tmp_path / ".claude" / "projects" / "-Users-x-play-lemonaid",
        {"sessionId": _SESSION, "firstPrompt": "z" * 200},
    )

    name = notify.get_session_name(_SESSION, cwd)
    assert name is not None
    assert name.endswith("...")
    assert len(name) == notify._NAME_MAX_LEN + 3


def test_no_index_yields_none(monkeypatch, tmp_path):
    _patch_home(monkeypatch, tmp_path)
    assert notify.get_session_name(_SESSION, "/Users/x/play/lemonaid") is None


def test_environment_name_upgraded_by_real_title():
    """A tmux/cwd placeholder is replaced once Claude produces a summary."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "t.db") as conn:
        db.add(
            conn,
            channel="claude:abc",
            message="Working",
            name="play-lemonaid",
            metadata={"name_source": "environment"},
        )
        updated = db.add(
            conn,
            channel="claude:abc",
            message="Waiting",
            name="Fix broken notification hook",
            metadata={"name_source": "claude_index"},
        )

        assert updated.name == "Fix broken notification hook"


def test_real_title_not_regressed_to_placeholder():
    """Once a real title is stored, a later environment name must not clobber it."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "t.db") as conn:
        db.add(
            conn,
            channel="claude:abc",
            message="Waiting",
            name="Fix broken notification hook",
            metadata={"name_source": "claude_index"},
        )
        updated = db.add(
            conn,
            channel="claude:abc",
            message="Working",
            name="play-lemonaid",
            metadata={"name_source": "environment"},
        )

        assert updated.name == "Fix broken notification hook"


def test_user_rename_survives_name_upgrade():
    """A rename always wins, but the tracked auto-name still improves."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "t.db") as conn:
        n = db.add(
            conn,
            channel="claude:abc",
            message="Working",
            name="play-lemonaid",
            metadata={"name_source": "environment"},
        )
        db.update_name(conn, n.id, "my-own-name")

        updated = db.add(
            conn,
            channel="claude:abc",
            message="Waiting",
            name="Fix broken notification hook",
            metadata={"name_source": "claude_index"},
        )
        assert updated.name == "my-own-name"
        assert updated.metadata["auto_name"] == "Fix broken notification hook"

        # Clearing the override restores the upgraded auto-name, not the placeholder.
        db.update_name(conn, n.id, None)
        cleared = db.get(conn, n.id)
        assert cleared is not None
        assert cleared.name == "Fix broken notification hook"


def test_refresh_auto_name_upgrades_placeholder():
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "t.db") as conn:
        n = db.add(
            conn,
            channel="claude:abc",
            message="Working",
            name="play-lemonaid",
            metadata={"name_source": "environment"},
        )

        assert db.refresh_auto_name(conn, n.id, "Add snooze function", notify.TITLE_SOURCE) is True
        after = db.get(conn, n.id)
        assert after is not None
        assert after.name == "Add snooze function"
        assert after.metadata["name_source"] == notify.TITLE_SOURCE

        # Idempotent: re-applying the same title changes nothing.
        assert db.refresh_auto_name(conn, n.id, "Add snooze function", notify.TITLE_SOURCE) is False


def test_rename_supersedes_an_existing_ai_title():
    """A /rename after Claude auto-titled the session must win."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "t.db") as conn:
        n = db.add(
            conn,
            channel="claude:abc",
            message="Working",
            name="Audit code for intermittent user issue",
            metadata={"name_source": notify.TITLE_SOURCE},
        )

        assert db.refresh_auto_name(conn, n.id, "annoying-refresh", notify.RENAME_SOURCE) is True
        after = db.get(conn, n.id)
        assert after is not None
        assert after.name == "annoying-refresh"
        assert after.metadata["name_source"] == notify.RENAME_SOURCE


def test_refresh_auto_name_keeps_user_rename():
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "t.db") as conn:
        n = db.add(conn, channel="claude:abc", message="Working", name="play-lemonaid")
        db.update_name(conn, n.id, "my-own-name")

        assert db.refresh_auto_name(conn, n.id, "Add snooze function", notify.TITLE_SOURCE) is True
        after = db.get(conn, n.id)
        assert after is not None
        assert after.name == "my-own-name"
        assert after.metadata["auto_name"] == "Add snooze function"


def test_refresh_auto_name_ignores_empty_title():
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "t.db") as conn:
        n = db.add(conn, channel="claude:abc", message="Working", name="play-lemonaid")

        assert db.refresh_auto_name(conn, n.id, "", notify.TITLE_SOURCE) is False
        assert db.get(conn, n.id).name == "play-lemonaid"  # type: ignore[union-attr]


def test_transcript_ai_title_wins_over_index(tmp_path, monkeypatch):
    """Current Claude records names in the transcript, not sessions-index.json."""
    cwd = "/Users/x/play/lemonaid"
    _patch_home(monkeypatch, tmp_path)
    project = tmp_path / ".claude" / "projects" / "-Users-x-play-lemonaid"
    _write_index(project, {"sessionId": _SESSION, "summary": "stale index summary"})
    (project / f"{_SESSION}.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"type": "user", "cwd": cwd}),
                json.dumps({"type": "ai-title", "aiTitle": "First guess"}),
                json.dumps({"type": "ai-title", "aiTitle": "Refined title"}),
            ]
        )
    )

    assert notify.get_session_name(_SESSION, cwd) == "Refined title"


def test_transcript_custom_title_wins_over_ai_title(tmp_path, monkeypatch):
    cwd = "/Users/x/play/lemonaid"
    _patch_home(monkeypatch, tmp_path)
    project = tmp_path / ".claude" / "projects" / "-Users-x-play-lemonaid"
    project.mkdir(parents=True)
    (project / f"{_SESSION}.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"type": "ai-title", "aiTitle": "Generated"}),
                json.dumps({"type": "custom-title", "customTitle": "my-rename"}),
            ]
        )
    )

    assert notify.get_session_name(_SESSION, cwd) == "my-rename"


def test_rename_wins_even_when_ai_title_comes_later(tmp_path, monkeypatch):
    """Claude keeps emitting ai-title entries after a /rename; the rename still wins."""
    cwd = "/Users/x/play/lemonaid"
    _patch_home(monkeypatch, tmp_path)
    project = tmp_path / ".claude" / "projects" / "-Users-x-play-lemonaid"
    project.mkdir(parents=True)
    (project / f"{_SESSION}.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"type": "custom-title", "customTitle": "my-rename"}),
                json.dumps({"type": "ai-title", "aiTitle": "Generated later"}),
            ]
        )
    )

    resolved = notify.resolve_session_name(_SESSION, cwd)
    assert resolved is not None
    assert resolved.name == "my-rename"
    assert resolved.source == notify.RENAME_SOURCE


def test_ai_title_reports_title_source(tmp_path, monkeypatch):
    cwd = "/Users/x/play/lemonaid"
    _patch_home(monkeypatch, tmp_path)
    project = tmp_path / ".claude" / "projects" / "-Users-x-play-lemonaid"
    project.mkdir(parents=True)
    (project / f"{_SESSION}.jsonl").write_text(
        json.dumps({"type": "ai-title", "aiTitle": "Generated"})
    )

    resolved = notify.resolve_session_name(_SESSION, cwd)
    assert resolved is not None
    assert resolved.source == notify.TITLE_SOURCE


def test_history_rename_wins_over_ai_title(tmp_path, monkeypatch):
    """A /rename recorded only in history.jsonl still beats an AI title."""
    cwd = "/Users/x/play/lemonaid"
    _patch_home(monkeypatch, tmp_path)
    project = tmp_path / ".claude" / "projects" / "-Users-x-play-lemonaid"
    project.mkdir(parents=True)
    (project / f"{_SESSION}.jsonl").write_text(
        json.dumps({"type": "ai-title", "aiTitle": "Generated"})
    )
    (tmp_path / ".claude" / "history.jsonl").write_text(
        json.dumps({"sessionId": _SESSION, "display": "/rename hand-picked"})
    )

    resolved = notify.resolve_session_name(_SESSION, cwd)
    assert resolved is not None
    assert resolved.name == "hand-picked"
    assert resolved.source == notify.RENAME_SOURCE


def test_transcript_without_title_falls_back_to_index(tmp_path, monkeypatch):
    """An early session has no title yet; the legacy index still helps if present."""
    cwd = "/Users/x/play/lemonaid"
    _patch_home(monkeypatch, tmp_path)
    project = tmp_path / ".claude" / "projects" / "-Users-x-play-lemonaid"
    _write_index(project, {"sessionId": _SESSION, "summary": "index summary"})
    (project / f"{_SESSION}.jsonl").write_text(json.dumps({"type": "user", "cwd": cwd}))

    assert notify.get_session_name(_SESSION, cwd) == "index summary"


def test_register_working_upgrades_name_too():
    """The submit hook path shares the same reconciliation."""
    with tempfile.TemporaryDirectory() as tmpdir, db.connect(Path(tmpdir) / "t.db") as conn:
        db.add(
            conn,
            channel="claude:abc",
            message="Working",
            name="play-lemonaid",
            metadata={"name_source": "environment"},
        )
        updated = db.register_working(
            conn,
            channel="claude:abc",
            message="Working",
            name="Fix broken notification hook",
            metadata={"name_source": "claude_index"},
        )

        assert updated.name == "Fix broken notification hook"
