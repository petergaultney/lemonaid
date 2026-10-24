"""The lemon in the focused pane is drawn whatever is collapsed, hidden, folded or searched away."""

import dataclasses
import time
from types import SimpleNamespace

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.config import load_config
from lemonaid.groups.store import Group
from lemonaid.inbox import db, presence
from lemonaid.inbox.tui.live import inbox_entries, inbox_frame
from lemonaid.inbox.tui.rows import brief_cards, pr_numbers
from lemonaid.stalls import inbox as stalls_inbox


def _session(conn, name: str) -> str:
    channel = f"claude:{name}"
    row = db.add(conn, channel, "msg", name, {"tty": f"/dev/{name}", "cwd": "/w"})
    conn.execute(
        "UPDATE notifications SET switch_source = 'tmux', status = 'read' WHERE id = ?", (row.id,)
    )
    conn.commit()
    return channel


def _brief(conn, channel: str, status: str, hidden: bool = False) -> None:
    name = channel.split(":")[1]
    path = brief_store.briefs_dir() / f"2026-10-23-{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Work\n\nBrief-ID: {name}.SampleBin\n\n{'Hidden: yes' if hidden else ''}\n\n"
        f"Status: {status}\n\n## Now\n"
    )
    identity.ensure(conn, path)
    attached.attach(conn, channel, path)


def _load(focused: set[str], search_text: str | None = None, fold: tuple[str, ...] = ("done",)):
    config = load_config()
    config = dataclasses.replace(
        config, tui=dataclasses.replace(config.tui, fold_statuses=list(fold))
    )
    with db.connect() as conn:
        return inbox_frame.load(
            conn,
            config,
            brief_cards.BriefCache(),
            presence.Probe(),
            pr_numbers.Cache(),
            stalls_inbox.Tracker(),
            env_filter="tmux",
            focused=frozenset(f"/dev/{name}" for name in focused),
            search_text=search_text,
            current_key=None,
            other_key=None,
            unfolded_ids=set(),
            shared_names=set(),
            now=time.time(),
        )


def test_a_focused_hidden_brief_is_shown_and_an_unfocused_one_is_not():
    with db.connect() as conn:
        _brief(conn, _session(conn, "quiet"), "waiting", hidden=True)
        _session(conn, "plain")

    assert [n.channel for n in _load({"quiet"}).shown] == ["claude:plain", "claude:quiet"]
    assert [n.channel for n in _load({"plain"}).shown] == ["claude:plain"]


def test_a_focused_lemon_with_a_folded_status_stays_out_of_the_fold():
    with db.connect() as conn:
        _brief(conn, _session(conn, "finished"), "done")

    assert [n.channel for n in _load({"finished"}).folded] == []
    assert [n.channel for n in _load(set()).folded] == ["claude:finished"]


def test_a_focused_lemon_matches_a_search_it_does_not_match():
    with db.connect() as conn:
        _session(conn, "alpha")
        _session(conn, "beta")

    frame = _load({"beta"}, search_text="alpha")

    assert {n.channel for n in frame.active.rows if n.id in (frame.matching_ids or set())} == {
        "claude:alpha",
        "claude:beta",
    }


def _entries_frame(group: Group, focused: frozenset[str]):
    return SimpleNamespace(
        matching_ids=None,
        pinned=frozenset(),
        parents={},
        other=[],
        groups=[group],
        focused_channels=focused,
        active=SimpleNamespace(
            memberships={"a1": ("A",), "a2": ("A",)},
            cards={},
            rows=[db.Notification(1, "a1", "", status="read"), db.Notification(2, "a2", "")],
            deaf=frozenset(),
        ),
    )


def test_a_focused_lemon_is_drawn_in_a_collapsed_group_and_the_group_stays_collapsed():
    group = Group(1, "A", 1.0, (), True)
    rows = _entries_frame(group, frozenset({"a2"})).active.rows

    entries, _, _ = inbox_entries.entries(
        _entries_frame(group, frozenset({"a2"})), rows, [], frozenset(), False
    )
    unfocused, _, _ = inbox_entries.entries(
        _entries_frame(group, frozenset()), rows, [], frozenset(), False
    )

    assert [e.key for e in entries] == ["group:1", "2@1"]
    assert [e.key for e in unfocused] == ["group:1"]
    assert entries[0].group.collapsed
    assert group.collapsed
