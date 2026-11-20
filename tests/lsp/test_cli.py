import argparse
import os
import sys

import pytest

import lemonaid.lsp
from lemonaid.front_end import location
from lemonaid.lsp import cli, registry


def test_lsp_without_the_extra_names_it(monkeypatch, capsys) -> None:
    monkeypatch.setitem(sys.modules, "lemonaid.lsp.server", None)
    monkeypatch.delattr(lemonaid.lsp, "server", raising=False)

    with pytest.raises(SystemExit) as exited:
        cli._lsp(argparse.Namespace())

    assert exited.value.code == 2
    assert "lemonaid-inbox[lsp]" in capsys.readouterr().err


def test_editor_commands_without_a_server_exit_1(capsys, tmp_path) -> None:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["editor", "open", str(tmp_path)])

    with pytest.raises(SystemExit) as exited:
        args.func(args)

    assert exited.value.code == 1
    assert "no editor server" in capsys.readouterr().err


def _open_in(monkeypatch, tmp_path, *, server_at: str, caller_at: str) -> list[dict]:
    """`lemonaid editor open` on a file outside the one server's root, with the server's
    terminal workspace and the caller's as given."""
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path / "state"))
    registry.write(
        registry.Record(
            pid=os.getpid(),
            socket="/nowhere.sock",
            roots=(str(tmp_path / "repo"),),
            location=location.Location("tmux", "/tmp/tmux-1/default", server_at),
            started=1.0,
        )
    )
    monkeypatch.setattr(
        cli.location, "here", lambda: location.Location("tmux", "/tmp/tmux-1/default", caller_at)
    )
    asked: list[dict] = []
    monkeypatch.setattr(
        cli.registry, "request", lambda record, message: asked.append(message) or {"shown": True}
    )
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["editor", "open", str(tmp_path / "notes" / "guide.md")])
    with pytest.raises(SystemExit):
        args.func(args)
    return asked


def test_editor_open_outside_every_root_goes_to_the_editor_in_your_workspace(
    monkeypatch, tmp_path
) -> None:
    asked = _open_in(monkeypatch, tmp_path, server_at="tools", caller_at="tools")

    assert [message["path"] for message in asked] == [
        str((tmp_path / "notes" / "guide.md").resolve())
    ]


def test_editor_open_outside_every_root_refuses_an_editor_elsewhere(
    monkeypatch, capsys, tmp_path
) -> None:
    asked = _open_in(monkeypatch, tmp_path, server_at="notes", caller_at="tools")

    assert asked == []
    assert "none runs in your terminal workspace" in capsys.readouterr().err


def test_nvim_path_prints_the_client_plugin_directory(capsys) -> None:
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["editor", "nvim-path"])

    with pytest.raises(SystemExit) as exited:
        args.func(args)

    plugin = cli.pathlib.Path(capsys.readouterr().out.strip())
    assert exited.value.code == 0
    assert (plugin / "lsp" / "lemonaid.lua").is_file()
    assert (plugin / "lua" / "lma" / "init.lua").is_file()
