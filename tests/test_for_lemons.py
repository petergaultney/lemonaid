"""`lemonaid for-lemons` has to work from an installed copy, not only a checkout.

An agent reaches lemonaid through the CLI and has no reason to know where a
markdown file lives on disk, so the guide has to be reachable by command.
"""

import argparse

import pytest

from lemonaid import for_lemons


def test_the_guide_is_findable():
    """Either installed beside the package or in a checkout - one of them must hit."""
    assert for_lemons.guide_path() is not None


def test_the_guide_is_the_one_humans_read():
    path = for_lemons.guide_path()

    assert path is not None
    assert path.name == "for-lemons.md"
    assert "Places" in path.read_text()


def test_it_prints_the_contents(capsys):
    for_lemons.cmd_for_lemons(argparse.Namespace(path=False))

    assert "Lemonaid for Lemons" in capsys.readouterr().out


def test_path_prints_a_location_instead(capsys):
    for_lemons.cmd_for_lemons(argparse.Namespace(path=True))

    printed = capsys.readouterr().out.strip()
    assert printed.endswith("for-lemons.md")
    assert "Lemonaid for Lemons" not in printed


def test_a_missing_guide_says_where_to_find_it(monkeypatch, capsys):
    monkeypatch.setattr(for_lemons, "guide_path", lambda: None)

    with pytest.raises(SystemExit):
        for_lemons.cmd_for_lemons(argparse.Namespace(path=False))

    assert "docs/for-lemons.md" in capsys.readouterr().err


def test_the_guide_covers_every_place_verb():
    """A verb an agent can call but can't read about is the gap this command closes."""
    text = for_lemons.guide_path().read_text()

    for verb in ("place open", "place list", "place toss", "place hooks"):
        assert verb in text
