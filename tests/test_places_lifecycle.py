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


def test_acquire_creates_and_returns_the_directory(tmp_path):
    (tmp_path / "fresh").mkdir()
    root = PlaceRoot(path=tmp_path, create="mkdir -p fresh", path_of=f"echo {tmp_path}/fresh")

    directory, error = lifecycle.acquire_key("fresh", root)

    assert error is None
    assert directory == tmp_path / "fresh"


def test_acquire_never_touches_tmux(monkeypatch, tmp_path):
    """The whole point: a caller that isn't a tmux client leaves no session behind."""
    (tmp_path / "d").mkdir()
    spawned = _spawns_into(monkeypatch)

    def _no_tmux(*args, **kwargs):
        raise AssertionError("acquire must not look at tmux")

    monkeypatch.setattr(lifecycle.tmux.navigation, "get_pane_for_cwd", _no_tmux)
    monkeypatch.setattr(lifecycle.tmux.navigation, "get_pane_for_session", _no_tmux)

    lifecycle.acquire_key("d", PlaceRoot(path=tmp_path, path_of=f"echo {tmp_path}/d"))

    assert not spawned


def test_acquire_is_idempotent_for_an_existing_directory(tmp_path):
    (tmp_path / "already").mkdir()
    root = PlaceRoot(
        path=tmp_path,
        create="echo SHOULD-NOT-RUN > created-marker",
        path_of=f"echo {tmp_path}/already",
    )

    directory, error = lifecycle.acquire_key("already", root)

    assert (directory, error) == (tmp_path / "already", None)
    assert not (tmp_path / "created-marker").exists()


def test_acquire_reports_a_root_that_cannot_create(tmp_path):
    directory, error = lifecycle.acquire_key("k", PlaceRoot(path=tmp_path))

    assert directory is None
    assert error and "No create command" in error


def test_acquire_reports_a_create_that_produced_nothing(tmp_path):
    root = PlaceRoot(path=tmp_path, create="true", path_of=f"echo {tmp_path}/never-made")

    directory, error = lifecycle.acquire_key("k", root)

    assert directory is None
    assert error and "Could not acquire" in error


def _no_session_named(monkeypatch) -> None:
    monkeypatch.setattr(
        lifecycle.tmux.navigation, "get_pane_for_session", lambda session: (None, None)
    )


def test_open_session_spawns_in_the_given_directory(monkeypatch, tmp_path):
    _no_session_named(monkeypatch)
    spawned = _spawns_into(monkeypatch)

    assert lifecycle.open_session("notes", tmp_path, _CONFIG) is None
    assert spawned[0]["cwd"] == str(tmp_path)
    assert spawned[0]["session_name"] == "notes"


def test_open_session_acquires_nothing(monkeypatch, tmp_path):
    """There is no root to create under; the directory is taken as given."""
    _no_session_named(monkeypatch)
    _spawns_into(monkeypatch)

    lifecycle.open_session("notes", tmp_path / "does-not-exist", _CONFIG)

    assert not (tmp_path / "does-not-exist").exists()


def test_open_session_reuses_by_name(monkeypatch, tmp_path):
    monkeypatch.setattr(
        lifecycle.tmux.navigation, "get_pane_for_session", lambda session: ("notes", "%7")
    )
    switched = []
    monkeypatch.setattr(
        lifecycle.tmux.navigation,
        "switch_to_pane",
        lambda session, pane, save_current=True: switched.append((session, pane)) or True,
    )
    spawned = _spawns_into(monkeypatch)

    assert lifecycle.open_session("notes", tmp_path, _CONFIG) is None
    assert switched == [("notes", "%7")]
    assert not spawned


def test_open_session_distinguishes_names_in_one_directory(monkeypatch, tmp_path):
    """Unlike a place, the directory is not the identity - the name is.

    Two named sessions in the same directory is normal here, so an existing
    session elsewhere in that directory must not be handed back.
    """
    asked: list[str] = []

    def _by_name(session):
        asked.append(session)
        return ("notes", "%7") if session == "notes" else (None, None)

    monkeypatch.setattr(lifecycle.tmux.navigation, "get_pane_for_session", _by_name)
    monkeypatch.setattr(
        lifecycle.tmux.navigation, "get_pane_for_cwd", lambda cwd, process=None: ("notes", "%7")
    )
    spawned = _spawns_into(monkeypatch)

    assert lifecycle.open_session("scratch", tmp_path, _CONFIG) is None
    assert asked == ["scratch"]
    assert spawned[0]["session_name"] == "scratch"


def test_open_session_looks_up_the_sanitized_name(monkeypatch, tmp_path):
    """tmux never sees the dots, so neither can the lookup that matches them."""
    asked: list[str] = []
    monkeypatch.setattr(
        lifecycle.tmux.navigation,
        "get_pane_for_session",
        lambda session: (asked.append(session), (None, None))[1],
    )
    _spawns_into(monkeypatch)

    lifecycle.open_session("v1.2:beta", tmp_path, _CONFIG)

    assert asked == ["v1-2-beta"]


def test_detached_open_does_not_switch(monkeypatch, tmp_path):
    _no_existing_session(monkeypatch)
    spawned = _spawns_into(monkeypatch)

    lifecycle.open_place(tmp_path, _CONFIG, attach=False)

    assert spawned[0]["attach"] is False


def test_open_place_refuses_an_ambiguous_directory(monkeypatch, tmp_path):
    """Two sessions with a window there means one of them is the one wanted.

    Spawning a third would be the opposite of resolving it, and `session` is a
    truthy sentinel here - the pane check alone would fall through to spawning.
    """
    monkeypatch.setattr(
        lifecycle.tmux.navigation,
        "get_pane_for_cwd",
        lambda cwd, process=None: (lifecycle.tmux.navigation.AMBIGUOUS, None),
    )
    spawned = _spawns_into(monkeypatch)

    error = lifecycle.open_place(tmp_path, _CONFIG)

    assert error and "not guessing" in error
    assert not spawned
