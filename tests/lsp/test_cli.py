import argparse
import sys

import pytest

import lemonaid.lsp
from lemonaid.lsp import cli


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
