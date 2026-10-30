"""A `ps` args line runs a harness when its program, or Node's script, is named for it."""

import pytest

from lemonaid.lemon_watchers import watcher


@pytest.mark.parametrize(
    ("args", "name", "expected"),
    [
        ("codex --no-daemon 'a launch prompt " + "word " * 5000 + "'", "codex", True),
        ("/opt/node/bin/node /opt/codex/bin/codex resume", "codex", True),
        ("'/Applications/My Tools/claude' --resume", "claude", True),
        ("claude 'an unbalanced quote", "claude", True),
        ("bash -c 'claude'", "claude", False),
        ("", "claude", False),
    ],
)
def test_only_the_leading_words_decide(args, name, expected):
    assert watcher.is_harness(args, name) is expected
