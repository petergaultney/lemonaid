import dataclasses

import pytest

from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.launch.restart import planning
from lemonaid.messages import recipient

from .. import shared


@pytest.fixture
def setup(tmp_path, monkeypatch):
    with db.connect() as conn:
        path, row, lemon_id, transcript = shared.setup(conn, tmp_path)
    target = dataclasses.replace(shared.TARGET, cwd=str(tmp_path))
    monkeypatch.setattr(planning.pane, "locate", lambda socket, tty: target)
    monkeypatch.setattr(planning.pane, "exit_option", lambda target: "")
    monkeypatch.setattr(planning.pane, "composer", lambda target, harness: None)
    monkeypatch.setattr(planning.pane, "model", lambda target, model: None)
    monkeypatch.setattr(
        planning.process,
        "inspect",
        lambda pid: shared.ROOT if pid == shared.ROOT.pid else shared.SOURCE,
    )
    monkeypatch.setattr(planning.process, "same", lambda source: True)
    monkeypatch.setattr(planning.process, "ancestry", lambda pid: [shared.SOURCE, shared.ROOT])
    monkeypatch.setattr(planning.process, "on_tty", lambda tty: [shared.SOURCE, shared.ROOT])
    monkeypatch.setattr(planning.launch_args, "argv", lambda pid: shared.SETTINGS["argv"])
    monkeypatch.setattr(
        planning.recipient, "probe", lambda *args: recipient.State(recipient.DEAF, "")
    )
    monkeypatch.setattr(planning.settings.shutil, "which", lambda name, **kwargs: name)
    return path, row, lemon_id, transcript


def test_deaf_session_can_plan_without_changing_row_brief_or_watchers(setup):
    path, before, lemon_id, _transcript = setup
    contents = path.read_bytes()
    with db.connect() as conn:
        plan = planning.build(conn, lemon_id, Config())
        assert db.get_by_channel(conn, shared.CHANNEL, unread_only=False) == before
        assert conn.execute("SELECT COUNT(*) FROM lemon_restarts").fetchone()[0] == 0
    assert path.read_bytes() == contents
    assert plan["session_id"] == shared.SESSION
    assert plan["lemon_id"] == lemon_id


@pytest.mark.parametrize("state", [recipient.MID_TURN, recipient.ASKING])
def test_force_overrides_only_turn_and_input_state(setup, monkeypatch, state):
    monkeypatch.setattr(planning.recipient, "probe", lambda *args: recipient.State(state, ""))
    with db.connect() as conn:
        with pytest.raises(ValueError, match="mid-turn"):
            planning.build(conn, shared.CHANNEL, Config())
        assert planning.build(conn, shared.CHANNEL, Config(), force=True)["force"]


@pytest.mark.parametrize("force", [False, True])
def test_force_never_overrides_missing_native_binding(setup, force):
    with db.connect() as conn:
        conn.execute("DELETE FROM harness_generations")
        conn.commit()
        with pytest.raises(ValueError, match="native process binding"):
            planning.build(conn, shared.CHANNEL, Config(), force=force)


def test_foreign_background_job_refuses_even_force(setup, monkeypatch):
    monkeypatch.setattr(
        planning.process,
        "on_tty",
        lambda tty: [shared.SOURCE, shared.ROOT, dataclasses.replace(shared.SOURCE, pid=999)],
    )
    with db.connect() as conn, pytest.raises(ValueError, match="Unmanaged jobs"):
        planning.build(conn, shared.CHANNEL, Config(), force=True)


def test_native_busy_transcript_refuses_despite_idle_row(setup):
    setup[3].write_text(
        setup[3].read_text() + '{"type":"event_msg","payload":{"type":"task_started"}}\n'
    )
    with db.connect() as conn, pytest.raises(ValueError, match="idle turn"):
        planning.build(conn, shared.CHANNEL, Config())
