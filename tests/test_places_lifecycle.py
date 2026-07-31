"""Opening a place is one path whether its directory exists yet or not."""

from lemonaid.config import Config, PlaceRoot, TmuxSessionConfig
from lemonaid.places import lifecycle

_CONFIG = Config(tmux_session=TmuxSessionConfig(templates={"default": ["", "claude"]}))


def _no_existing_session(monkeypatch) -> None:
    monkeypatch.setattr(
        lifecycle.tmux.navigation, "get_pane_for_cwd", lambda cwd, process=None: (None, None)
    )


def _spawns_into(monkeypatch, error: str | None = None) -> list[dict]:
    spawned: list[dict] = []

    def _spawn(**kwargs):
        spawned.append(kwargs)
        return error

    monkeypatch.setattr(lifecycle.tmux.session, "spawn_session", _spawn)
    return spawned


def test_open_place_switches_to_an_existing_session(monkeypatch, tmp_path):
    monkeypatch.setattr(
        lifecycle.tmux.navigation, "get_pane_for_cwd", lambda cwd, process=None: ("live", "%2")
    )
    switched = []

    def _switch(session, pane, save_current=True):
        switched.append((session, pane))
        return True

    monkeypatch.setattr(lifecycle.tmux.navigation, "switch_to_pane", _switch)
    spawned = _spawns_into(monkeypatch)

    assert lifecycle.open_place(tmp_path, _CONFIG) is None
    assert switched == [("live", "%2")]
    assert not spawned


def test_open_place_spawns_when_nothing_is_there(monkeypatch, tmp_path):
    _no_existing_session(monkeypatch)
    spawned = _spawns_into(monkeypatch)

    assert lifecycle.open_place(tmp_path, _CONFIG, session_name="named") is None
    assert spawned[0]["cwd"] == str(tmp_path)
    assert spawned[0]["session_name"] == "named"


def test_open_key_acquires_then_opens(monkeypatch, tmp_path):
    (tmp_path / "acquired").mkdir()
    root = PlaceRoot(path=tmp_path, create="mkdir -p acquired", path_of=f"echo {tmp_path}/acquired")
    _no_existing_session(monkeypatch)
    spawned = _spawns_into(monkeypatch)

    directory, error = lifecycle.open_key("acquired", _CONFIG, root)

    assert error is None
    assert directory == tmp_path / "acquired"
    assert spawned[0]["cwd"] == str(tmp_path / "acquired")


def test_open_key_opens_an_existing_directory_without_creating(monkeypatch, tmp_path):
    """Asking for a session for something that already exists must be safe."""
    (tmp_path / "already").mkdir()
    root = PlaceRoot(
        path=tmp_path,
        create="echo SHOULD-NOT-RUN > created-marker",
        path_of=f"echo {tmp_path}/already",
    )
    _no_existing_session(monkeypatch)
    _spawns_into(monkeypatch)

    directory, error = lifecycle.open_key("already", _CONFIG, root)

    assert error is None
    assert directory == tmp_path / "already"
    assert not (tmp_path / "created-marker").exists()


def test_open_key_reports_a_root_that_cannot_create(monkeypatch, tmp_path):
    _no_existing_session(monkeypatch)
    _spawns_into(monkeypatch)

    directory, error = lifecycle.open_key("k", _CONFIG, PlaceRoot(path=tmp_path))

    assert directory is None
    assert error and "No create command" in error


def test_open_key_reports_a_create_that_produced_nothing(monkeypatch, tmp_path):
    root = PlaceRoot(path=tmp_path, create="true", path_of=f"echo {tmp_path}/never-made")
    _no_existing_session(monkeypatch)
    _spawns_into(monkeypatch)

    directory, error = lifecycle.open_key("k", _CONFIG, root)

    assert directory is None
    assert error and "Could not acquire" in error


def test_open_key_passes_the_spawn_error_through(monkeypatch, tmp_path):
    (tmp_path / "d").mkdir()
    root = PlaceRoot(path=tmp_path, path_of=f"echo {tmp_path}/d")
    _no_existing_session(monkeypatch)
    _spawns_into(monkeypatch, error="name already exists")

    directory, error = lifecycle.open_key("d", _CONFIG, root)

    assert directory == tmp_path / "d"
    assert error == "name already exists"


def test_detached_open_does_not_switch(monkeypatch, tmp_path):
    _no_existing_session(monkeypatch)
    spawned = _spawns_into(monkeypatch)

    lifecycle.open_place(tmp_path, _CONFIG, attach=False)

    assert spawned[0]["attach"] is False
