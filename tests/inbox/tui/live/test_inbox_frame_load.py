"""One inbox refresh reads the live sessions once, for both the main table and the other pane."""

import time

import pytest

from lemonaid.config import load_config
from lemonaid.inbox import db, presence, view
from lemonaid.inbox.tui.live import inbox_frame
from lemonaid.inbox.tui.rows import brief_cards, pr_numbers
from lemonaid.stalls import inbox as stalls_inbox

from . import shared


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
    from lemonaid.grove.source import inputs

    with db.connect() as conn:
        db.add(conn, "claude:here", "msg", "here", {"cwd": "/w"}, switch_source="tmux")
        db.add(conn, "claude:there", "msg", "there", {"cwd": "/w"}, switch_source="wezterm")
        groups.store.add(conn, groups.store.create(conn, "G"), ["claude:here"])
    doc = tmp_path / "g.md"
    doc.write_text("# G\n")
    shared.add_item(doc, "claude:here")
    shared.add_item(doc, "claude:there")
    here_reply, there_reply = (
        shared.item_channel(doc, "claude:here"),
        shared.item_channel(doc, "claude:there"),
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
    with db.connect() as conn:
        db.add(conn, "claude:there", "msg", "there", {"cwd": "/w"}, switch_source="wezterm")
    doc = tmp_path / "g.md"
    doc.write_text("# G\n")
    shared.add_item(doc, "claude:there")
    shared.add_item(doc, "claude:gone")
    shared.add_item(doc)

    with db.connect() as conn:
        frame = _load_in_tmux(conn)

    others = [n.channel for n in frame.other]
    mine = [n.channel for n in frame.active.rows]
    assert others == ["claude:there", shared.item_channel(doc, "claude:there")]
    assert shared.item_channel(doc, "claude:gone") in mine and shared.item_channel(doc) in mine
    assert shared.item_channel(doc, "claude:there") not in mine


def test_a_reply_whose_lemon_has_no_terminal_shows_on_its_own(tmp_path):
    with db.connect() as conn:
        db.add(conn, "claude:headless", "msg", "headless", {"cwd": "/w"})
    doc = tmp_path / "g.md"
    doc.write_text("# G\n")
    shared.add_item(doc, "claude:headless")

    with db.connect() as conn:
        frame = _load_in_tmux(conn)

    reply = shared.item_channel(doc, "claude:headless")
    assert reply in [n.channel for n in frame.active.rows]
    assert reply not in frame.attached


def test_attention_mode_keeps_a_reply_to_read_out_of_the_fold(tmp_path):
    with db.connect() as conn:
        db.add(conn, "claude:here", "msg", "here", {"cwd": "/w"}, switch_source="tmux")
    doc = tmp_path / "g.md"
    doc.write_text("# G\n")
    shared.add_item(doc, "claude:here")
    shared.add_item(doc, "claude:away")
    shared.read_item(doc, "claude:away")

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
    assert shared.item_channel(doc, "claude:here") in shown
    assert "claude:here" in folded  # the layout brings it back above its reply
    assert shared.item_channel(doc, "claude:away") not in shown


def test_a_reply_row_already_read_leaves_the_inbox(tmp_path):
    with db.connect() as conn:
        db.add(conn, "claude:here", "msg", "here", {"cwd": "/w"}, switch_source="tmux")
    read_doc, unread_doc = tmp_path / "read.md", tmp_path / "unread.md"
    shared.add_item(read_doc, "claude:here")
    shared.add_item(unread_doc, "claude:here")
    shared.read_item(read_doc, "claude:here")

    with db.connect() as conn:
        frame = _load_in_tmux(conn)

    channels = [n.channel for n in frame.active.rows]
    assert shared.item_channel(read_doc, "claude:here") not in channels
    assert shared.item_channel(unread_doc, "claude:here") in channels


@pytest.mark.parametrize("hide_when_read", [False, True])
def test_a_read_item_in_the_other_pane_stays_unless_it_asked_to_go(tmp_path, hide_when_read):
    with db.connect() as conn:
        db.add(conn, "claude:there", "msg", "there", {"cwd": "/w"}, switch_source="wezterm")
    doc = tmp_path / "g.md"
    doc.write_text("# G\n")
    item = shared.add_item(doc, "claude:there", hide_when_read=hide_when_read)
    shared.read_item(doc, "claude:there")

    with db.connect() as conn:
        frame = _load_in_tmux(conn)

    expected = ["claude:there"] if hide_when_read else ["claude:there", item]
    assert [n.channel for n in frame.other] == expected
