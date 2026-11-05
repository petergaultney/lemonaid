import pytest

from lemonaid.claude import launch_args, trust
from lemonaid.config import BackendConfig, Config, PlaceRoot, PlacesConfig
from lemonaid.inbox import db
from lemonaid.launch.move import planning
from lemonaid.launch.move.destination import Destination
from lemonaid.launch.restart import native, process
from lemonaid.restore import launch

from ..restart import shared

_DEDICATED = Config(
    backends={"codex": BackendConfig(resume_command="codex --no-daemon resume {session_id}")}
)


@pytest.fixture
def destination(tmp_path, monkeypatch):
    with db.connect() as conn:
        shared.setup(conn, tmp_path / "source")
    monkeypatch.setattr(process, "same", lambda *a: True)
    monkeypatch.setattr(launch_args, "argv", lambda pid: ["codex", "--no-daemon"])
    target = tmp_path / "dest"
    target.mkdir()
    return Destination(str(target), "feat/dest", "tmux", "feat/dest")


def _launches_in_destination(monkeypatch, calls):
    def resume(row, config, prompt, *, dedicated=False):
        calls.append((row, prompt))
        return launch.Launch(row.metadata["cwd"], 'codex --no-daemon resume x "$P"', {}, True)

    monkeypatch.setattr(launch, "launch", resume)


def test_resumes_with_the_destination_recorded(destination, monkeypatch):
    calls = []
    _launches_in_destination(monkeypatch, calls)
    with db.connect() as conn:
        plan = planning.build(conn, shared.CHANNEL, destination, _DEDICATED)
    row, prompt = calls[0]
    assert row.metadata["cwd"] == destination.directory
    assert row.metadata["tmux_session"] == "feat/dest"
    assert destination.directory in prompt
    assert plan["patch"] == {"cwd": destination.directory, "tmux_session": "feat/dest"}
    assert plan["kind"] == "move"
    assert plan["claude_trust"] is False
    assert plan["from"]["tty"] == shared.TARGET.tty


def test_refuses_a_lemon_already_there(destination, monkeypatch, tmp_path):
    _launches_in_destination(monkeypatch, [])
    here = Destination(str(tmp_path / "source"), "", "tmux", "test")
    with db.connect() as conn, pytest.raises(ValueError, match="already works"):
        planning.build(conn, shared.CHANNEL, here, _DEDICATED)


def test_refuses_mid_turn_without_force(destination, monkeypatch):
    _launches_in_destination(monkeypatch, [])
    with db.connect() as conn:
        conn.execute("UPDATE notifications SET turn_at = 123")
        conn.commit()
        with pytest.raises(ValueError, match="mid-turn"):
            planning.build(conn, shared.CHANNEL, destination, _DEDICATED)
        assert planning.build(conn, shared.CHANNEL, destination, _DEDICATED, True)


def test_refuses_a_resume_that_lands_elsewhere(destination, monkeypatch):
    monkeypatch.setattr(
        launch, "launch", lambda row, *a, **k: launch.Launch("/tmp", "codex --no-daemon", {}, True)
    )
    with db.connect() as conn, pytest.raises(ValueError, match="cannot resume in the destination"):
        planning.build(conn, shared.CHANNEL, destination, _DEDICATED)


def test_refuses_a_shared_app_server_resume(destination):
    with db.connect() as conn, pytest.raises(ValueError, match="no-daemon"):
        planning.build(conn, shared.CHANNEL, destination, Config())


def test_plans_a_dedicated_resume_with_the_real_builder(destination):
    with db.connect() as conn:
        plan = planning.build(conn, shared.CHANNEL, destination, _DEDICATED)
    assert "--no-daemon" in plan["line"]
    assert f"--cd {destination.directory}" in plan["line"]


def test_refuses_without_a_process_binding(destination, monkeypatch):
    _launches_in_destination(monkeypatch, [])
    monkeypatch.setattr(native, "binding", lambda *a: None)
    with db.connect() as conn, pytest.raises(ValueError, match="fresh hook"):
        planning.build(conn, shared.CHANNEL, destination, _DEDICATED, True)


def _claude_move(tmp_path, monkeypatch) -> Destination:
    monkeypatch.setattr(shared, "CHANNEL", "claude:" + shared.SESSION)
    with db.connect() as conn:
        shared.setup(conn, tmp_path / "source")
    monkeypatch.setattr(process, "same", lambda *a: True)
    monkeypatch.setattr(launch_args, "argv", lambda pid: ["claude"])
    monkeypatch.setattr(trust, "config_file", lambda: tmp_path / "missing.json")
    _launches_in_destination(monkeypatch, [])
    target = tmp_path / "places" / "dest"
    target.mkdir(parents=True)
    return Destination(str(target), "dest", "tmux", "dest")


def test_refuses_a_claude_destination_claude_does_not_trust(tmp_path, monkeypatch):
    to = _claude_move(tmp_path, monkeypatch)
    config = Config(places=PlacesConfig(roots=[PlaceRoot(tmp_path / "places")]))
    with db.connect() as conn, pytest.raises(ValueError, match="folder-trust prompt"):
        planning.build(conn, shared.CHANNEL, to, config)


def test_plans_to_trust_a_destination_its_root_lets_claude_trust(tmp_path, monkeypatch):
    to = _claude_move(tmp_path, monkeypatch)
    config = Config(places=PlacesConfig(roots=[PlaceRoot(tmp_path / "places", claude_trust=True)]))
    with db.connect() as conn:
        plan = planning.build(conn, shared.CHANNEL, to, config)
    assert plan["claude_trust"] is True
