"""How `place open` reads its argument.

Inside a root that has a key vocabulary the argument is a key, and a miss means
acquire. Outside every such root no root could have meant it, so it names a
session in the current directory and nothing is acquired. The distinction is
what keeps a mistyped key from silently becoming an empty session.
"""

import argparse
import json

import pytest

from lemonaid.config import Config, PlaceRoot, PlacesConfig, TmuxSessionConfig
from lemonaid.places import cli, lifecycle


def _args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(
        **{"key": "thing", "root": None, "detach": False, "json": False, **kwargs}
    )


def _config(*roots: PlaceRoot) -> Config:
    return Config(
        tmux_session=TmuxSessionConfig(templates={"default": [""]}),
        places=PlacesConfig(roots=list(roots)),
    )


def _records(monkeypatch, config: Config, cwd) -> tuple[list, list]:
    monkeypatch.setattr(cli, "load_config", lambda: config)
    monkeypatch.setattr(cli.Path, "cwd", staticmethod(lambda: cwd))

    keyed: list = []
    monkeypatch.setattr(
        lifecycle,
        "open_key",
        lambda key, cfg, root, attach=True: (keyed.append((key, root.path, attach)), (cwd, None))[
            1
        ],
    )

    sessions: list = []
    monkeypatch.setattr(
        lifecycle,
        "open_session",
        lambda name, directory, cfg, attach=True: sessions.append((name, directory, attach)),
    )

    return keyed, sessions


def test_a_key_inside_a_namespaced_root(monkeypatch, tmp_path):
    root = PlaceRoot(path=tmp_path, path_of="wt path {key}", create="wt co {key}")
    keyed, sessions = _records(monkeypatch, _config(root), tmp_path / "sub")

    cli.cmd_open(_args(key="feat/thing"))

    assert keyed == [("feat/thing", tmp_path, True)]
    assert not sessions


def test_a_name_outside_every_root(monkeypatch, tmp_path):
    keyed, sessions = _records(monkeypatch, _config(), tmp_path)

    cli.cmd_open(_args(key="notes"))

    assert sessions == [("notes", tmp_path, True)]
    assert not keyed


def test_a_hookless_root_does_not_claim_the_name(monkeypatch, tmp_path):
    """It has no vocabulary, so being inside it is the same as being outside one."""
    keyed, sessions = _records(monkeypatch, _config(PlaceRoot(path=tmp_path)), tmp_path)

    cli.cmd_open(_args(key="notes"))

    assert sessions == [("notes", tmp_path, True)]
    assert not keyed


def test_the_innermost_root_decides(monkeypatch, tmp_path):
    """A plain clone checked out inside a worktree repo is not part of its namespace."""
    outer = PlaceRoot(path=tmp_path, path_of="wt path {key}")
    inner = PlaceRoot(path=tmp_path / "vendored")
    (tmp_path / "vendored").mkdir()
    keyed, sessions = _records(monkeypatch, _config(outer, inner), tmp_path / "vendored")

    cli.cmd_open(_args(key="notes"))

    assert sessions == [("notes", tmp_path / "vendored", True)]
    assert not keyed


def test_an_explicit_root_is_still_required_to_resolve(monkeypatch, tmp_path, capsys):
    """--root asks for a vocabulary by name; a root without one is an error, not a session."""
    _, sessions = _records(monkeypatch, _config(), tmp_path)

    with pytest.raises(SystemExit):
        cli.cmd_open(_args(key="notes", root=str(tmp_path)))

    assert not sessions
    assert "No places root configured" in capsys.readouterr().err


def test_detach_is_passed_through(monkeypatch, tmp_path):
    _, sessions = _records(monkeypatch, _config(), tmp_path)

    cli.cmd_open(_args(key="notes", detach=True))

    assert sessions == [("notes", tmp_path, False)]


def test_json_reports_no_root_for_a_plain_session(monkeypatch, tmp_path, capsys):
    _records(monkeypatch, _config(), tmp_path)

    cli.cmd_open(_args(key="notes", json=True))

    assert json.loads(capsys.readouterr().out) == {
        "key": "notes",
        "dir": str(tmp_path),
        "root": None,
        "error": None,
    }


def _acquire_args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**{"key": "thing", "root": None, "json": False, **kwargs})


def test_acquire_prints_the_directory(monkeypatch, tmp_path, capsys):
    root = PlaceRoot(path=tmp_path, path_of="echo x")
    monkeypatch.setattr(cli, "load_config", lambda: _config(root))
    monkeypatch.setattr(cli.Path, "cwd", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(lifecycle, "acquire_key", lambda key, r: (tmp_path / key, None))

    cli.cmd_acquire(_acquire_args(key="feat/thing"))

    assert capsys.readouterr().out.strip() == str(tmp_path / "feat/thing")


def test_acquire_outside_a_namespaced_root_is_an_error(monkeypatch, tmp_path, capsys):
    """There is no key vocabulary here, so nothing could be acquired."""
    monkeypatch.setattr(cli, "load_config", lambda: _config())
    monkeypatch.setattr(cli.Path, "cwd", staticmethod(lambda: tmp_path))

    with pytest.raises(SystemExit):
        cli.cmd_acquire(_acquire_args(key="notes"))

    assert "no directory to acquire" in capsys.readouterr().err


def test_acquire_exits_nonzero_on_failure(monkeypatch, tmp_path, capsys):
    root = PlaceRoot(path=tmp_path, path_of="echo x")
    monkeypatch.setattr(cli, "load_config", lambda: _config(root))
    monkeypatch.setattr(cli.Path, "cwd", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(lifecycle, "acquire_key", lambda key, r: (None, "no create command"))

    with pytest.raises(SystemExit):
        cli.cmd_acquire(_acquire_args(key="nope", json=True))

    assert json.loads(capsys.readouterr().out)["error"] == "no create command"
