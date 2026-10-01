"""The key that opens the brief popup also closes it."""

from lemonaid.brief import dismiss

_TABLE = """\
bind-key    -T prefix b       run-shell -b "lemonaid brief show \\"#{session_name}\\" --popup"
bind-key    -T prefix m       run-shell -b "lemonaid mark-read --tty \\"#{pane_tty}\\""
bind-key -r -T prefix B       run-shell -b "lemonaid brief show --popup"
"""


def test_each_prefix_pairs_with_each_brief_key():
    assert dismiss.sequences(["`", "C-b"], _TABLE) == ["` b", "` B", "ctrl+b b", "ctrl+b B"]


def test_a_key_tmux_escapes_is_the_character_itself():
    assert dismiss.sequences(["C-a"], "bind-key -T prefix \\# run-shell 'lemonaid brief show'") == [
        "ctrl+a #"
    ]


def test_sequences_come_back_as_pairs():
    assert dismiss.pairs(["ctrl+b b", "` B", "lonely"]) == [("ctrl+b", "b"), ("`", "B")]


def test_keys_it_cannot_translate_are_left_out():
    assert dismiss.sequences(["F12"], _TABLE) == []
    assert dismiss.sequences(["`"], "bind-key -T prefix M-b run-shell 'lemonaid brief show'") == []
