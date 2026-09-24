"""The key that opens the brief popup also closes it."""

from lemonaid.brief import dismiss

_TABLE = """\
bind-key    -T prefix b       run-shell -b "lemonaid brief show \\"#{session_name}\\" --popup"
bind-key    -T prefix m       run-shell -b "lemonaid mark-read --tty \\"#{pane_tty}\\""
bind-key -r -T prefix B       run-shell -b "lemonaid brief show --popup"
"""


def test_each_prefix_pairs_with_each_brief_key():
    assert dismiss.sequences(["`", "C-b"], _TABLE) == ["`b", "`B", "^Bb", "^BB"]


def test_lesskey_specials_are_escaped():
    assert dismiss.sequences(["C-a"], "bind-key -T prefix \\# run-shell 'lemonaid brief show'") == [
        "^A\\#"
    ]


def test_keys_lesskey_cannot_express_are_left_out():
    assert dismiss.sequences(["F12"], _TABLE) == []
    assert dismiss.sequences(["`"], "bind-key -T prefix M-b run-shell 'lemonaid brief show'") == []
