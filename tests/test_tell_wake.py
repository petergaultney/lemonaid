"""`tell --wake` brings back a finished lemon; `--wake-parent` goes up when it can't be."""

import argparse
import subprocess
import time
from pathlib import Path

import pytest

from lemonaid.brief import archive, attached, identity, lemon
from lemonaid.brief import store as brief_store
from lemonaid.config import Config, PlaceRoot, PlacesConfig
from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.messages import autoresume_tmux, cli, recipient, store, tell_delivery, waiter
from lemonaid.places import audit
from lemonaid.restore import plan

_CHILD = "claude:child"
_PARENT = "codex:parent"


@pytest.fixture(autouse=True)
def _world(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:sender")
    monkeypatch.setattr(tell_delivery.service, "ensure_running", lambda: None)
    monkeypatch.setattr(
        recipient, "_tty_commands", lambda tty: ["codex"] if tty.endswith("901") else ["-fish"]
    )
    monkeypatch.setattr(plan, "transcript_missing", lambda row: False)
    monkeypatch.setattr(
        autoresume_tmux.tmux,
        "run",
        lambda args, socket=None, **kw: subprocess.CompletedProcess(args, 0, "", ""),
    )
    monkeypatch.setattr(
        tell_delivery, "load_config", lambda: Config(places=PlacesConfig(roots=[_root(tmp_path)]))
    )


@pytest.fixture
def started(monkeypatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(
        autoresume_tmux, "start", lambda row, config, text: calls.append(row.channel) or ""
    )
    return calls


def _root(tmp_path: Path) -> PlaceRoot:
    return PlaceRoot(path=tmp_path, create="mkdir -p {key}", path_of="cd {key} && pwd")


def _lemon(name: str, channel: str, brief: str, tty: str, cwd: Path) -> tuple[Path, str]:
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(brief)
    metadata = {"tty": tty, "cwd": str(cwd), "tmux_session": name, "session_id": name}
    with db.connect() as conn:
        db.add(conn, channel, "", metadata=metadata, switch_source="tmux")
        attached.attach(conn, channel, path)
        return path.resolve(), identity.ensure(conn, path)


def _child(tmp_path: Path, status: str = "working") -> tuple[Path, str]:
    return _lemon("child", _CHILD, f"# c\n\nStatus: {status}\n", "/dev/ttys900", tmp_path)


def _archive(path: Path, channel: str) -> None:
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
        assert row is not None
        db.archive(conn, row.id, "place-teardown")
        archive.archive(conn, path, time.time(), {channel}, why="test")


def _tell(*argv: str) -> int:
    parser = argparse.ArgumentParser()
    cli.add_tell_parser(parser.add_subparsers())
    args = parser.parse_args(["tell", *argv])
    try:
        args.func(args)
    except SystemExit as exit:
        return int(exit.code or 0)

    return 0


def _pending(lemon_id: str) -> list[str]:
    return [path.read_text() for path in sorted(store.mailbox_for_id(lemon_id).glob("*.md"))]


def test_an_archived_lemon_gets_the_message_and_the_wake_flag(capsys, tmp_path, started):
    path, lemon_id = _child(tmp_path)
    _archive(path, _CHILD)

    assert _tell(lemon_id, "hello") == 1

    assert started == []
    assert len(_pending(lemon_id)) == 1
    assert "run the same `lemonaid tell` with --wake" in capsys.readouterr().err
    with db.connect() as conn:
        assert archive.is_archived(lemon.brief_of(conn, lemon_id))


def test_rerunning_with_wake_starts_it_without_a_second_copy(capsys, tmp_path, started):
    path, lemon_id = _child(tmp_path)
    _archive(path, _CHILD)
    assert _tell(lemon_id.split(".")[0], "hello") == 1

    assert _tell(lemon_id.split(".")[0], "hello", "--wake") == 0

    assert started == [_CHILD]
    assert len(_pending(lemon_id)) == 1
    with db.connect() as conn:
        assert attached.by_channel(conn, [_CHILD]) == {_CHILD: path}
    assert "It reads the message once it is up" in capsys.readouterr().err


def test_wake_starts_a_done_lemon(tmp_path, started):
    _child(tmp_path, status="done")

    assert _tell(_CHILD, "hello") == 1
    assert _tell(_CHILD, "hello", "--wake") == 0
    assert started == [_CHILD]


def test_an_unwakeable_lemon_points_at_wake_parent(capsys, tmp_path, started, monkeypatch):
    monkeypatch.setattr(plan, "transcript_missing", lambda row: True)
    path, lemon_id = _child(tmp_path)
    _archive(path, _CHILD)

    assert _tell(lemon_id, "hello", "--wake") == 1

    assert started == []
    err = capsys.readouterr().err
    assert "transcript is gone" in err
    assert f"lemonaid tell --wake-parent {lemon_id} <message>" in err


def test_wake_parent_sends_to_the_nearest_lemon_that_will_read_it(capsys, tmp_path, started):
    path, child_id = _child(tmp_path)
    _, parent_id = _lemon("parent", _PARENT, "# p\n\nStatus: working\n", "/dev/ttys901", tmp_path)
    with db.connect() as conn:
        links.set_parent(conn, child_id, parent_id)
    _archive(path, _CHILD)

    with waiter.armed(store.mailbox_for_id(parent_id)):
        assert _tell(child_id, "hello", "--wake-parent") == 0

    assert started == []
    [message] = _pending(parent_id)
    assert f"This was meant for {child_id}, which can't be woken.\n\nhello" in message
    assert _pending(child_id) == []


def test_wake_parent_without_a_parent_fails(capsys, tmp_path, started):
    _, lemon_id = _child(tmp_path)

    assert _tell(lemon_id, "hello", "--wake-parent") == 1
    assert "has no parent" in capsys.readouterr().err


def _failing_place(tmp_path, monkeypatch) -> Path:
    """A directory the places log names, under a root whose hooks fail."""
    root = PlaceRoot(path=tmp_path, create="false", path_of="false")
    monkeypatch.setattr(
        tell_delivery, "load_config", lambda: Config(places=PlacesConfig(roots=[root]))
    )
    audit.record("open", "created", key="feat", directory=str(tmp_path / "feat"))
    return tmp_path / "feat"


def test_a_failed_acquire_leaves_the_brief_in_the_attic_and_can_be_retried(
    capsys, tmp_path, started, monkeypatch
):
    place = _failing_place(tmp_path, monkeypatch)
    path, lemon_id = _lemon("child", _CHILD, "# c\n\nStatus: done\n", "/dev/ttys900", place)
    _archive(path, _CHILD)

    assert _tell(lemon_id, "hello", "--wake") == 1

    assert started == []
    with db.connect() as conn:
        assert archive.is_archived(lemon.brief_of(conn, lemon_id))
        assert attached.by_channel(conn, [_CHILD]) == {}
    err = capsys.readouterr().err
    assert "could not be recreated" in err
    assert "--wake-parent" not in err
    assert "Don't send it again" in err

    place.mkdir()
    assert _tell(lemon_id, "hello", "--wake") == 0

    assert started == [_CHILD]
    assert len(_pending(lemon_id)) == 1


def test_wake_parent_skips_an_ancestor_whose_transcript_is_gone(tmp_path, started, monkeypatch):
    monkeypatch.setattr(plan, "transcript_missing", lambda row: row.channel == "claude:parent")
    _, child_id = _child(tmp_path)
    _, parent_id = _lemon(
        "parent", "claude:parent", "# p\n\nStatus: working\n", "/dev/ttys902", tmp_path
    )
    _, top_id = _lemon("top", _PARENT, "# t\n\nStatus: working\n", "/dev/ttys901", tmp_path)
    with db.connect() as conn:
        links.set_parent(conn, child_id, parent_id)
        links.set_parent(conn, parent_id, top_id)

    with waiter.armed(store.mailbox_for_id(top_id)):
        assert _tell(child_id, "hello", "--wake-parent") == 0

    assert started == []
    assert len(_pending(top_id)) == 1


def test_wake_parent_stops_at_an_ancestor_a_retry_could_bring_back(
    capsys, tmp_path, started, monkeypatch
):
    place = _failing_place(tmp_path, monkeypatch)
    _, child_id = _child(tmp_path)
    _, parent_id = _lemon(
        "parent", "claude:parent", "# p\n\nStatus: working\n", "/dev/ttys902", place
    )
    _, top_id = _lemon("top", _PARENT, "# t\n\nStatus: working\n", "/dev/ttys901", tmp_path)
    with db.connect() as conn:
        links.set_parent(conn, child_id, parent_id)
        links.set_parent(conn, parent_id, top_id)

    assert _tell(child_id, "hello", "--wake-parent") == 1

    assert started == []
    assert len(_pending(parent_id)) == 1
    assert _pending(top_id) == []
