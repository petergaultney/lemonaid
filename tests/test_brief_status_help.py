"""`brief status --help` explains each status a lemon may set."""

import argparse

import pytest

from lemonaid.brief import store, verbs_cli

_MEANINGS = {
    "blocked": "the user can act now",
    "alert": "harm grows while it waits",
    "review": "a teammate's approving review",
    "approve": "sets no status while the PR waits on its author or merge",
    "merge": "only the user's merge remains",
    "running": "minding a long pipeline or process",
    "done": "an open PR is never done",
}


def _status_help(capsys) -> str:
    parser = argparse.ArgumentParser()
    verbs_cli.add_parsers(parser.add_subparsers())
    with pytest.raises(SystemExit):
        parser.parse_args(["status", "--help"])

    return " ".join(capsys.readouterr().out.split())


def test_help_describes_every_status_a_lemon_may_set(capsys):
    assert set(_MEANINGS) == set(store.STATES)

    out = _status_help(capsys)

    assert all(f"{state} " in out and meaning in out for state, meaning in _MEANINGS.items())
