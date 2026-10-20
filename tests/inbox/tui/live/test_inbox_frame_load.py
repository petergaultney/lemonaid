"""One inbox refresh reads the live sessions once, for both the main table and the other pane."""

import time

from lemonaid.config import load_config
from lemonaid.inbox import db, presence, view
from lemonaid.inbox.tui.live import inbox_frame
from lemonaid.inbox.tui.rows import brief_cards, pr_numbers
from lemonaid.stalls import inbox as stalls_inbox


def test_main_table_and_other_pane_come_from_one_read(monkeypatch):
    with db.connect() as conn:
        for channel, source in (
            ("claude:here-a", "tmux"),
            ("claude:there", "wezterm"),
            ("claude:headless", None),
            ("claude:here-b", "tmux"),
        ):
            db.add(conn, channel, "msg", channel, {"cwd": "/w"}, switch_source=source)

    reads = []
    original = view.ordered_active

    def counted(conn, switch_source, *args):
        reads.append(switch_source)
        return original(conn, switch_source, *args)

    monkeypatch.setattr(view, "ordered_active", counted)
    with db.connect() as conn:
        frame = inbox_frame.load(
            conn,
            load_config(),
            brief_cards.BriefCache(),
            presence.Probe(),
            pr_numbers.Cache(),
            stalls_inbox.Tracker(),
            env_filter="tmux",
            focused=frozenset(),
            search_text=None,
            current_key=None,
            other_key=None,
            unfolded_ids=set(),
            shared_names=set(),
            now=time.time(),
        )

    assert reads == [None]
    assert [n.channel for n in frame.active.rows] == ["claude:here-b", "claude:here-a"]
    assert [n.channel for n in frame.shown] == ["claude:here-b", "claude:here-a"]
    assert [n.channel for n in frame.other] == ["claude:there"]
