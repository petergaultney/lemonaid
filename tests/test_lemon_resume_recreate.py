"""`lemon resume --recreate` puts back what a toss took before resuming the lemon."""

import argparse
import subprocess
import time
from pathlib import Path

import pytest

from lemonaid.brief import archive, attached, identity, lemon
from lemonaid.brief import store as brief_store
from lemonaid.config import Config, PlaceRoot, PlacesConfig
from lemonaid.inbox import db
from lemonaid.messages import autoresume_tmux, recipient, recreate, resume_cli
from lemonaid.places import audit

_CHANNEL = "claude:tossed"


@pytest.fixture(autouse=True)
def _caller(monkeypatch):
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:caller")
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["-fish"])  # nothing runs there


@pytest.fixture
def started(monkeypatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(
        autoresume_tmux, "start", lambda row, config, text: calls.append(row.channel) or ""
    )
    return calls


@pytest.fixture
def tmux(monkeypatch) -> list[list[str]]:
    """Every tmux command `autoresume_tmux.recreate` runs, against a server with no sessions."""
    calls: list[list[str]] = []

    def run(args, socket=None, **kwargs):
        calls.append([str(socket), *args])
        return subprocess.CompletedProcess(args, 1 if args[0] == "has-session" else 0, "", "")

    monkeypatch.setattr(autoresume_tmux.tmux, "run", run)
    return calls


@pytest.fixture
def root(tmp_path, monkeypatch) -> PlaceRoot:
    """A root whose hooks make and find a directory per key, and the config naming it."""
    found = PlaceRoot(
        path=(tmp_path / "repo").resolve(),
        create="mkdir -p {key}",
        path_of="test -d {key} && cd {key} && pwd",
    )
    found.path.mkdir()
    monkeypatch.setattr(
        resume_cli, "load_config", lambda: Config(places=PlacesConfig(roots=[found]))
    )
    return found


def _lemon(cwd: Path) -> tuple[Path, str]:
    path = brief_store.briefs_dir() / "tossed.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# t\n\nStatus: working\n")
    metadata = {
        "tty": "/dev/ttys900",
        "cwd": str(cwd),
        "tmux_session": "feat-x",
        "tmux_socket": "/tmp/work.sock",
        "session_id": "tossed",
    }
    with db.connect() as conn:
        db.add(conn, _CHANNEL, "", metadata=metadata, switch_source="tmux")
        attached.attach(conn, _CHANNEL, path)
        return path.resolve(), identity.ensure(conn, path)


def _toss(path: Path) -> None:
    with db.connect() as conn:
        row = db.get_by_channel(conn, _CHANNEL, unread_only=False)
        assert row is not None
        db.archive(conn, row.id, "place-teardown")
        archive.archive(conn, path, time.time(), {_CHANNEL})


def _resume(*argv: str) -> int:
    parser = argparse.ArgumentParser()
    resume_cli.add_parser(parser.add_subparsers())
    args = parser.parse_args(["resume", *argv])
    try:
        args.func(args)
    except SystemExit as exit:
        return int(exit.code or 0)

    return 0


def test_an_archived_brief_without_recreate_names_the_flag(capsys, started, root, tmux):
    path, lemon_id = _lemon(root.path)
    _toss(path)

    assert _resume(lemon_id) == 1
    assert started == []
    assert f"lemon resume {lemon_id} --recreate" in capsys.readouterr().err


def test_recreate_revives_the_brief_onto_its_session_and_the_tmux_session(
    capsys, started, root, tmux
):
    path, lemon_id = _lemon(root.path)
    _toss(path)

    assert _resume(lemon_id.split(".")[0], "--recreate") == 0

    assert started == [_CHANNEL]
    with db.connect() as conn:
        assert attached.by_channel(conn, [_CHANNEL]) == {_CHANNEL: path}
        assert lemon.brief_of(conn, lemon_id) == path
    assert ["/tmp/work.sock", "new-session", "-d", "-s", "feat-x", "-c", str(root.path)] in tmux
    out = capsys.readouterr().out
    assert "revived tossed.md" in out
    assert "recreated tmux session feat-x" in out


def test_a_live_tmux_session_is_left_alone(started, root, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        autoresume_tmux.tmux,
        "run",
        lambda args, socket=None: calls.append(args[0]) or subprocess.CompletedProcess(args, 0),
    )
    _lemon(root.path)

    assert _resume(_CHANNEL, "--recreate") == 0
    assert calls == ["has-session"]
    assert started == [_CHANNEL]


def test_a_released_directory_comes_back_through_its_roots_hooks(capsys, started, root, tmux):
    place = root.path / "feat-x"
    audit.record("open", "created", key="feat-x", directory=str(place), session="feat-x")
    _lemon(place / "src")

    assert _resume(_CHANNEL, "--recreate") == 1  # the directory is back, but not its src/
    assert place.is_dir()
    assert "'feat-x' is back" in capsys.readouterr().err

    (place / "src").mkdir()
    assert _resume(_CHANNEL, "--recreate") == 0
    assert started == [_CHANNEL]


def test_a_directory_the_places_log_does_not_name_is_refused(capsys, started, root, tmux):
    _lemon(root.path / "feat-x")

    assert _resume(_CHANNEL, "--recreate") == 1
    assert started == []
    assert tmux == []
    assert not (root.path / "feat-x").exists()
    assert "can't tell which place it was" in capsys.readouterr().err


def test_without_recreate_nothing_is_recreated(started, root, tmux):
    audit.record("open", "created", key="feat-x", directory=str(root.path / "feat-x"))
    _lemon(root.path / "feat-x")

    assert _resume(_CHANNEL) == 0
    assert tmux == []
    assert not (root.path / "feat-x").exists()


def test_the_innermost_latest_place_holding_the_directory_wins():
    events = [
        {"action": "open", "key": "outer", "dir": "/r/outer"},
        {"action": "open", "key": "old", "dir": "/r/outer/inner"},
        {"action": "toss", "key": "new", "dir": "/r/outer/inner"},
        {"action": "open", "key": "", "dir": "/r/outer/inner/deeper"},
    ]

    assert recreate.place_of(Path("/r/outer/inner/deeper"), events) == recreate.Place(
        "new", Path("/r/outer/inner")
    )


def test_a_session_now_holding_another_brief_keeps_it(capsys, started, root, tmux, monkeypatch):
    monkeypatch.setattr(recipient, "_tty_commands", lambda tty: ["claude"])
    path, lemon_id = _lemon(root.path)
    _toss(path)
    newer = brief_store.briefs_dir() / "newer.md"
    newer.write_text("# newer\n\nStatus: working\n")
    with db.connect() as conn:
        attached.attach(conn, _CHANNEL, newer)

    assert _resume(lemon_id, "--recreate") == 1

    assert started == []
    with db.connect() as conn:
        assert attached.by_channel(conn, [_CHANNEL]) == {_CHANNEL: newer.resolve()}
        assert archive.is_archived(lemon.brief_of(conn, lemon_id))
    assert "has another brief attached now (newer.md)" in capsys.readouterr().err
