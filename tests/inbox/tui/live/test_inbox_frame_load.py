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


def _load_in_tmux(conn):
    return inbox_frame.load(
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


def test_a_lemon_s_reply_row_comes_with_it_and_takes_its_groups(tmp_path):
    from lemonaid import groups
    from lemonaid.comments import notice
    from lemonaid.grove.source import inputs

    with db.connect() as conn:
        db.add(conn, "claude:here", "msg", "here", {"cwd": "/w"}, switch_source="tmux")
        db.add(conn, "claude:there", "msg", "there", {"cwd": "/w"}, switch_source="wezterm")
        groups.store.add(conn, groups.store.create(conn, "G"), ["claude:here"])
    doc = tmp_path / "g.md"
    doc.write_text("# G\n")
    notice.replied(doc, "Here (Author)", "One", "ok", lemon="claude:here")
    notice.replied(doc, "There (Author)", "Two", "ok", lemon="claude:there")
    here_reply, there_reply = (
        notice.channel(doc, "claude:here"),
        notice.channel(doc, "claude:there"),
    )

    with db.connect() as conn:
        frame = _load_in_tmux(conn)
        grove_rows = inputs.from_frame(conn, frame).rows

    channels = [n.channel for n in frame.active.rows]
    assert here_reply in channels and there_reply not in channels
    assert frame.attached == {here_reply: "claude:here", there_reply: "claude:there"}
    assert frame.active.memberships[here_reply] == frame.active.memberships["claude:here"] == ("G",)
    assert here_reply not in [n.channel for n in grove_rows]


def test_a_reply_row_goes_where_its_lemon_is_or_on_its_own_when_it_has_none(tmp_path):
    from lemonaid.comments import notice

    with db.connect() as conn:
        db.add(conn, "claude:there", "msg", "there", {"cwd": "/w"}, switch_source="wezterm")
    doc = tmp_path / "g.md"
    doc.write_text("# G\n")
    notice.replied(doc, "There (Author)", "One", "ok", lemon="claude:there")
    notice.replied(doc, "Gone (Author)", "Two", "ok", lemon="claude:gone")
    notice.replied(doc, "Old (Author)", "Three", "ok")

    with db.connect() as conn:
        frame = _load_in_tmux(conn)

    others = [n.channel for n in frame.other]
    mine = [n.channel for n in frame.active.rows]
    assert others == ["claude:there", notice.channel(doc, "claude:there")]
    assert notice.channel(doc, "claude:gone") in mine and notice.channel(doc) in mine
    assert notice.channel(doc, "claude:there") not in mine


def test_a_reply_whose_lemon_has_no_terminal_shows_on_its_own(tmp_path):
    from lemonaid.comments import notice

    with db.connect() as conn:
        db.add(conn, "claude:headless", "msg", "headless", {"cwd": "/w"})
    doc = tmp_path / "g.md"
    doc.write_text("# G\n")
    notice.replied(doc, "Headless (Author)", "One", "ok", lemon="claude:headless")

    with db.connect() as conn:
        frame = _load_in_tmux(conn)

    reply = notice.channel(doc, "claude:headless")
    assert reply in [n.channel for n in frame.active.rows]
    assert reply not in frame.attached


def test_attention_mode_keeps_a_reply_to_read_out_of_the_fold(tmp_path):
    from lemonaid.comments import notice

    with db.connect() as conn:
        db.add(conn, "claude:here", "msg", "here", {"cwd": "/w"}, switch_source="tmux")
    doc = tmp_path / "g.md"
    doc.write_text("# G\n")
    notice.replied(doc, "Here (Author)", "One", "to read", lemon="claude:here")
    notice.replied(doc, "Away (Author)", "Two", "read already", lemon="claude:away")
    notice.seen(doc, ["Two"])

    with db.connect() as conn:
        frame = inbox_frame.load(
            conn,
            load_config(),
            brief_cards.BriefCache(),
            presence.Probe(),
            pr_numbers.Cache(),
            stalls_inbox.Tracker(),
            env_filter=None,
            focused=frozenset(),
            search_text=None,
            current_key=None,
            other_key=None,
            unfolded_ids=set(),
            shared_names=set(),
            now=time.time(),
            attention_mode=True,
        )

    shown, folded = [n.channel for n in frame.shown], [n.channel for n in frame.folded]
    assert notice.channel(doc, "claude:here") in shown
    assert "claude:here" in folded  # the layout brings it back above its reply
    assert notice.channel(doc, "claude:away") not in shown
