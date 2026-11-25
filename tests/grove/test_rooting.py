from lemonaid.front_end import chat
from lemonaid.grove.source import rooting
from lemonaid.inbox import db


def _row(channel: str, session: str) -> db.Notification:
    return db.Notification(
        id=hash(channel) % 1000,
        channel=channel,
        message="",
        metadata={"tmux_session": session, "cwd": "/work"},
        switch_source="tmux",
    )


ROWS = [_row("claude:host", "richer"), _row("codex:guest", "window"), _row("claude:other", "x")]
IDS = {"claude:host": "SillyOil.richer", "codex:guest": "StoveHub.review"}


def test_a_lemon_grafted_by_lemon_id_stands_on_its_hosts_tree():
    roots = rooting.rooted(ROWS, IDS, {"StoveHub.review": "SillyOil.richer"})
    assert roots["codex:guest"] == ("richer", "richer", "SillyOil.richer")
    assert roots["claude:host"] == ("richer", "richer", "")


def test_a_graft_by_channel_holds_for_a_lemon_without_a_brief():
    roots = rooting.rooted(ROWS, IDS, {"claude:other": "codex:guest"})
    assert roots["claude:other"] == ("window", "window", "codex:guest")


def test_a_graft_onto_a_lemon_that_isnt_live_waits_on_its_own_tree():
    roots = rooting.rooted(ROWS, IDS, {"StoveHub.review": "GoneAway.slug"})
    assert roots["codex:guest"] == ("window", "window", "")


def test_a_lemon_follows_its_host_onto_the_hosts_own_host_and_a_loop_stays_home():
    chain = {"claude:other": "StoveHub.review", "StoveHub.review": "SillyOil.richer"}
    assert rooting.rooted(ROWS, IDS, chain)["claude:other"] == (
        "richer",
        "richer",
        "StoveHub.review",
    )
    loop = {"StoveHub.review": "SillyOil.richer", "SillyOil.richer": "StoveHub.review"}
    assert {c: r.key for c, r in rooting.rooted(ROWS, IDS, loop).items()} == {
        "claude:host": "richer",
        "codex:guest": "window",
        "claude:other": "x",
    }


def test_each_chat_conversation_is_its_own_tree_though_they_share_a_directory():
    rooms = [
        db.Notification(
            id=n,
            channel=f"openclaw:agent:main:matrix:channel:!{n}:grove.example",
            message="",
            name=name,
            metadata={"cwd": "/srv/agent-home"},
            switch_source=chat.NAME,
        )
        for n, name in ((1, "Dam valves"), (2, "Tree map"))
    ]

    roots = rooting.rooted(rooms, {}, {})

    assert [roots[room.channel] for room in rooms] == [
        (rooms[0].channel, "Dam valves", ""),
        (rooms[1].channel, "Tree map", ""),
    ]
