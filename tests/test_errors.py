"""CLI failures use the same persistent error log as the TUI."""

import sys

import pytest

from lemonaid import cli


def test_cli_failure_logs_and_reraises(monkeypatch, tmp_path):
    failure = ValueError("config failed")

    def crash(args):
        raise failure

    monkeypatch.setattr(sys, "argv", ["lemonaid", "config", "show"])
    monkeypatch.setattr(cli, "cmd_config_show", crash)
    for _ in range(2):
        with pytest.raises(ValueError) as caught:
            cli.main()
        assert caught.value is failure
    logged = (tmp_path / "state" / "logs" / "errors.log").read_text()
    assert logged.count("ValueError: config failed") == 2
    assert logged.count("lemonaid config show") == 2
