import argparse

from lemonaid import config, keys
from lemonaid.inbox.tui import bindings
from lemonaid.tmux import cli


def test_scratch_view_defaults_to_the_inbox():
    assert config.TmuxSessionConfig().scratch_view == "inbox"


def test_i_returns_to_the_inbox_from_a_brief():
    assert config.KeybindingsConfig().inbox == "i"


def test_scratch_accepts_a_view_flag():
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())

    assert parser.parse_args(["tmux", "scratch", "--view", "brief"]).view == "brief"


def test_an_inbox_key_taken_by_another_binding_is_reported_not_warned_about(capsys):
    kb = config.KeybindingsConfig(up_down="ri")

    assert keys.inbox_key_collisions(kb) == ["inbox", "brief"]
    assert not [w for w in keys.conflicts(kb) if "inbox'" in w]


def test_the_default_inbox_key_collides_with_nothing():
    assert keys.inbox_key_collisions(config.KeybindingsConfig()) == []


def test_the_inbox_action_runs_while_a_brief_is_shown():
    for unselected in (False, True):
        assert bindings.permitted(
            "inbox",
            brief_shown=True,
            overlaid=False,
            searching=False,
            history_focused=lambda: False,
            resume_available=lambda: False,
            brief_unselected=unselected,
        )
