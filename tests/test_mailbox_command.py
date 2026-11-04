import argparse

import pytest

from lemonaid.messages import mailbox_command
from lemonaid.watch import registry, stop_cli


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["inbox", "watch", "--self"], ["mailbox", "watch", "--self"]),
        (["inbox", "next", "--self"], ["mailbox", "next", "--self"]),
        (["inbox", "deliver"], ["mailbox", "deliver"]),
        (["inbox", "list"], ["inbox", "list"]),
        (["inbox"], ["inbox"]),
        (["watch", "inbox"], ["watch", "inbox"]),
    ],
)
def test_only_the_message_commands_move_from_inbox_to_mailbox(argv, expected):
    assert mailbox_command.canonical(argv) == expected


def test_a_brief_waiter_in_either_spelling_is_the_mailbox_watch():
    assert mailbox_command.runs_watch("lemonaid mailbox watch --self")
    assert mailbox_command.runs_watch("lemonaid inbox watch --self")
    assert not mailbox_command.runs_watch("lemonaid inbox list")
    assert not mailbox_command.runs_watch("lemonaid watch --self")
    assert not mailbox_command.runs_watch("lemonaid mailbox watch 'unclosed")


def test_watch_stop_takes_the_old_kind_name():
    parser = argparse.ArgumentParser()
    stop_cli.add_parser(parser.add_subparsers())

    assert parser.parse_args(["stop", "--self", "inbox"]).kind == "mailbox"
    assert registry.canonical_kind("inbox") == "mailbox"
