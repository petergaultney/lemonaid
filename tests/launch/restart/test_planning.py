import dataclasses

import pytest

from lemonaid.claude import launch_args
from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.launch.restart import cli, native, pane, planning, process, state
from lemonaid.restore import launch

from . import shared


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    with db.connect() as conn:
        shared.setup(conn, tmp_path)
    target = dataclasses.replace(shared.TARGET, cwd=str(tmp_path))
    monkeypatch.setattr(pane, "locate", lambda *a: target)
    monkeypatch.setattr(pane, "exit_option", lambda *a: "")
    monkeypatch.setattr(process, "inspect", lambda *a: shared.ROOT)
    monkeypatch.setattr(process, "same", lambda *a: True)
    monkeypatch.setattr(
        process, "ancestry", lambda pid: [shared.SOURCE, shared.ROOT] if pid == 101 else []
    )
    monkeypatch.setattr(process, "on_tty", lambda *a: [shared.SOURCE, shared.ROOT])
    monkeypatch.setattr(process, "descendants", lambda *a: [])
    monkeypatch.setattr(
        launch_args, "argv", lambda pid: ["codex", "--no-daemon"] if pid == 101 else ["zsh"]
    )
    return target


def test_uses_existing_resume_builder_and_extra_instruction(prepared, monkeypatch):
    calls = []

    def resume(row, config, prompt, *, dedicated=False):
        assert dedicated
        calls.append(prompt)
        return launch.Launch(
            prepared.cwd, 'custom-resume "$LEMONAID_PROMPT"', {"LEMONAID_PROMPT": prompt}, True
        )

    monkeypatch.setattr(launch, "launch", resume)
    with db.connect() as conn:
        result = planning.build(conn, shared.CHANNEL, Config())
    assert result["line"].startswith("custom-resume")
    assert "Rearm any watchers or other transient state" in calls[0]
    assert "model" not in result and "settings" not in result


def test_refuses_stale_process_even_with_force(prepared, monkeypatch):
    monkeypatch.setattr(process, "same", lambda *a: False)
    with db.connect() as conn, pytest.raises(ValueError, match="no longer owns"):
        planning.build(conn, shared.CHANNEL, Config(), True)


def test_refuses_unrelated_terminal_job(prepared, monkeypatch):
    monkeypatch.setattr(
        process,
        "on_tty",
        lambda *a: [shared.SOURCE, shared.ROOT, dataclasses.replace(shared.SOURCE, pid=999)],
    )
    with db.connect() as conn, pytest.raises(ValueError, match="Unrelated"):
        planning.build(conn, shared.CHANNEL, Config(), True)


def test_harness_owns_its_tool_shutdown(prepared, monkeypatch):
    tool = dataclasses.replace(shared.SOURCE, pid=999, parent=101, executable="sleep")
    monkeypatch.setattr(process, "on_tty", lambda *a: [shared.SOURCE, shared.ROOT, tool])
    monkeypatch.setattr(process, "descendants", lambda *a: [tool])
    with db.connect() as conn:
        assert planning.build(conn, shared.CHANNEL, Config(), True)["source"]["pid"] == 101


def test_non_force_refuses_known_mid_turn(prepared):
    with db.connect() as conn:
        conn.execute("UPDATE notifications SET turn_at = 123")
        conn.commit()
        with pytest.raises(ValueError, match="mid-turn"):
            planning.build(conn, shared.CHANNEL, Config())
        assert planning.build(conn, shared.CHANNEL, Config(), True)


def test_missing_binding_refuses_before_any_signal(prepared, monkeypatch):
    monkeypatch.setattr(native, "binding", lambda *a: None)
    with db.connect() as conn, pytest.raises(ValueError, match="fresh hook"):
        planning.build(conn, shared.CHANNEL, Config(), True)


def test_archived_partial_restart_reports_inspectable_operation(prepared, capsys):
    import argparse

    from lemonaid.messages import revive

    token = state.reserve(shared.plan())
    state.update(token, "partial", error="Unmanaged jobs remain")
    with db.connect() as conn:
        row = db.get_by_channel(conn, shared.CHANNEL, unread_only=False)
        db.archive(conn, row.id)
    hint = revive.revive(row, prepared.cwd, True, Config(), "").why
    assert f"--status {token} --json" in hint
    with db.connect() as conn, pytest.raises(ValueError, match=token):
        planning.build(conn, shared.CHANNEL, Config())
    cli._cmd(argparse.Namespace(status=token, json=True))
    assert token in capsys.readouterr().out
