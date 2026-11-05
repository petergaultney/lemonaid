import subprocess

import pytest

from lemonaid.config import Config, PlaceRoot, PlacesConfig
from lemonaid.launch.move import destination
from lemonaid.places import hooks, lifecycle
from lemonaid.tmux import relocation

_TMUX = {"tmux_session": "src", "tmux_socket": "/tmp/sock", "tty": "/dev/ttys001"}


def _panes(monkeypatch, lines: str, sessions: frozenset[str] = frozenset()):
    def run(args, socket=None, **kwargs):
        if args[0] == "has-session":
            found = args[2].removeprefix("=") in sessions
            return subprocess.CompletedProcess(args, 0 if found else 1, "", "")
        return subprocess.CompletedProcess(args, 0, lines, "")

    monkeypatch.setattr(relocation.command, "run", run)


def test_a_path_names_a_directory_and_a_new_session(tmp_path, monkeypatch):
    _panes(monkeypatch, "src\t/elsewhere\n")
    to = destination.resolve(str(tmp_path), None, _TMUX, "tmux", Config(), acquire=False)
    assert to.directory == str(tmp_path.resolve())
    assert to.key == ""
    assert to.workspace and to.workspace != "src"


def test_joins_the_session_already_working_there(tmp_path, monkeypatch):
    _panes(monkeypatch, f"src\t/elsewhere\nauthor\t{tmp_path.resolve()}/sub\n")
    to = destination.resolve(str(tmp_path), None, _TMUX, "tmux", Config(), acquire=False)
    assert to.workspace == "author"


def test_ignores_protected_sessions(tmp_path, monkeypatch):
    _panes(monkeypatch, f"hq\t{tmp_path.resolve()}\n")
    config = Config(places=PlacesConfig(protected_sessions=["hq"]))
    to = destination.resolve(str(tmp_path), None, _TMUX, "tmux", config, acquire=False)
    assert to.workspace != "hq"


def test_refuses_several_sessions(tmp_path, monkeypatch):
    _panes(monkeypatch, f"a\t{tmp_path.resolve()}\nb\t{tmp_path.resolve()}\n")
    with pytest.raises(ValueError, match="Several tmux sessions"):
        destination.resolve(str(tmp_path), None, _TMUX, "tmux", Config(), acquire=False)


def test_refuses_a_same_named_session_elsewhere(tmp_path, monkeypatch):
    _panes(monkeypatch, "feat-x\t/elsewhere\n", frozenset({"feat/x"}))
    monkeypatch.setattr(hooks, "directory_for_key", lambda root, key: tmp_path)
    root = PlaceRoot(path=tmp_path)
    with pytest.raises(ValueError, match="exists but has no pane"):
        destination.resolve("feat/x", root, _TMUX, "tmux", Config(), acquire=False)


def test_a_key_is_acquired_only_for_a_real_move(tmp_path, monkeypatch):
    acquired = []
    monkeypatch.setattr(hooks, "directory_for_key", lambda root, key: None)
    monkeypatch.setattr(
        lifecycle, "acquire_key", lambda key, root: acquired.append(key) or (tmp_path, None)
    )
    root = PlaceRoot(path=tmp_path)
    with pytest.raises(ValueError, match="does not exist"):
        destination.resolve("feat/x", root, {}, "cmux", Config(), acquire=False)
    to = destination.resolve("feat/x", root, {}, "cmux", Config(), acquire=True)
    assert acquired == ["feat/x"]
    assert (to.key, to.front_end, to.workspace) == ("feat/x", "cmux", "feat/x")


def test_a_key_needs_a_root():
    with pytest.raises(ValueError, match="--root"):
        destination.resolve("feat/x", None, {}, "cmux", Config(), acquire=True)
