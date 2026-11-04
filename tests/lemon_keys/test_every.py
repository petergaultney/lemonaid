"""The keys `grove key` reads match the inbox's in the same terminal, and differ in another."""

import itertools
import os
import time
from pathlib import Path

import pytest

from lemonaid import groups
from lemonaid.brief import attached
from lemonaid.brief import store as brief_store
from lemonaid.config import load_config
from lemonaid.grove.source import live
from lemonaid.inbox import db, presence
from lemonaid.inbox.tui.live import inbox_frame
from lemonaid.inbox.tui.rows import brief_cards, pr_numbers
from lemonaid.lemon_keys import lookup
from lemonaid.stalls import inbox as stalls_inbox

_ids = itertools.count(7300)


@pytest.fixture(autouse=True)
def _config():
    Path(os.environ["LEMONAID_CONFIG"]).write_text("")


def _grouped(name: str, source: str, group: str) -> None:
    channel = f"claude:{name}"
    with db.connect() as conn:
        n = db.add(
            conn,
            channel,
            "a message",
            name,
            {"tty": f"/dev/ttys{next(_ids)}", "cwd": "/tmp", "tmux_session": name},
            switch_source=source,
        )
        conn.execute(
            "UPDATE notifications SET status = 'read', created_at = ? WHERE id = ?",
            (time.time(), n.id),
        )
        path = brief_store.briefs_dir() / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# work\n\n## Now\n")
        attached.attach(conn, channel, path)
        try:
            found = groups.store.find(conn, group)
        except LookupError:
            found = groups.store.create(conn, group)
        groups.store.add(conn, found, [channel])
        conn.commit()


def _inbox_keys(env_filter: str) -> dict[str, str]:
    with db.connect() as conn:
        frame = inbox_frame.load(
            conn,
            load_config(),
            brief_cards.BriefCache(),
            presence.Probe(),
            pr_numbers.Cache(),
            stalls_inbox.Tracker(),
            env_filter=env_filter,
            focused=frozenset(),
            search_text=None,
            current_key=None,
            other_key=None,
            unfolded_ids=set(),
            shared_names=set(),
            now=time.time(),
        )
    grove = live.from_inbox(lambda: frame, load_config(), cards=False)()
    return {k.lemon.channel: k.key for k in lookup.every(grove.blocks, grove.arrangement)}


def _command_keys(terminal: str) -> dict[str, str]:
    grove = live.preview(load_config(), terminal)
    return {k.lemon.channel: k.key for k in lookup.every(grove.blocks, grove.arrangement)}


def test_each_terminal_reads_keys_as_its_own_inbox_shows_them():
    _grouped("cmux-worker", "cmux", "first")
    _grouped("tmux-worker", "tmux", "second")

    for terminal in ("cmux", "tmux"):
        assert _command_keys(terminal) == _inbox_keys(terminal)
    assert _command_keys("cmux")["claude:cmux-worker"][0] == "1"
    assert _command_keys("tmux")["claude:tmux-worker"][0] == "1"  # block 1 is another group here
