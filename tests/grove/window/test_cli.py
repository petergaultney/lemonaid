import argparse
import sys

import pytest

from lemonaid.grove.window import cli, control


def _run(*argv):
    parser = argparse.ArgumentParser()
    cli.add_parsers(parser.add_subparsers())
    args = parser.parse_args(["window", *argv])
    args.func(args)


def test_the_window_runs_on_macos_only(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(SystemExit, match="macOS only"):
        _run("run")


def test_without_the_web_extra_run_says_how_to_install_it(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "lemonaid.grove.window.app", None)  # no pywebview

    with pytest.raises(SystemExit, match=r"lemonaid-inbox\[web\]"):
        _run("run")


def test_show_with_no_window_running_says_how_to_start_one(monkeypatch, tmp_path):
    monkeypatch.setattr(control, "socket_path", lambda: tmp_path / "none.sock")

    with pytest.raises(SystemExit, match="grove window run"):
        _run("show", "--client", "/dev/ttys004")


def test_binding_prints_the_tmux_lines_for_the_key_asked_or_space(capsys):
    _run("binding", "--key", "W")
    assert "  bind-key W run-shell -b " in capsys.readouterr().out

    _run("binding")
    assert "  bind-key Space run-shell -b " in capsys.readouterr().out
