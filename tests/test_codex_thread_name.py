"""A Codex lemon's thread carries the name lemonaid shows for it."""

import json

import pytest

from lemonaid.codex import notify, thread_name
from lemonaid.inbox import db, emoji
from tests import codex_fakes

_THREAD = "01a1f6f1-aed3-7cf2-b97d-b553250d5e44"
_CHANNEL = f"codex:{_THREAD}"


@pytest.fixture
def stored() -> dict[str, str]:
    """Each thread's name in the test's Codex."""
    return {}


@pytest.fixture
def names(monkeypatch, stored) -> list[tuple[str, str]]:
    return codex_fakes.names_set(monkeypatch, stored)


def _lemon(name: str) -> None:
    with db.connect() as conn:
        db.add(conn, _CHANNEL, "Waiting", name=name, metadata={"session_id": _THREAD})
        conn.execute(
            "INSERT INTO lemon_identities (lemon_id, path) VALUES ('FilmyBoy.work', '/b.md')"
        )
        conn.execute(
            "INSERT INTO session_briefs (channel, path, attached_at) VALUES (?, '/b.md', 0)",
            (_CHANNEL,),
        )
        conn.commit()


def _hook(event: str) -> None:
    notify.handle_turn_hook(json.dumps({"hook_event_name": event, "session_id": _THREAD}))


def test_a_prompt_gives_the_thread_the_lemon_s_name(stored, names):
    _lemon("Remote names")
    with db.connect() as conn:
        emoji.set_emoji(conn, _CHANNEL, "🦊")
    stored[_THREAD] = "Accept Oria handoff brief"

    _hook("UserPromptSubmit")

    assert names == [(_THREAD, "🦊 Remote names (FilmyBoy)")]


def test_a_rename_reaches_the_thread_at_the_next_prompt_only(stored, names):
    _lemon("Remote names")
    stored[_THREAD] = "Remote names (FilmyBoy)"
    with db.connect() as conn:
        db.update_name(conn, db.get_by_channel(conn, _CHANNEL, unread_only=False).id, "Renamed")

    _hook("PreToolUse")
    assert names == []

    _hook("UserPromptSubmit")
    assert names == [(_THREAD, "Renamed (FilmyBoy)")]


def test_a_name_codex_replaced_is_set_again_whatever_the_snapshot_says(
    codex_records, stored, names
):
    _lemon("Remote names")
    codex_records[_THREAD] = codex_fakes.thread(_THREAD, name="Remote names (FilmyBoy)")
    stored[_THREAD] = "Codex's generated title"

    thread_name.push(_THREAD)

    assert names == [(_THREAD, "Remote names (FilmyBoy)")]


def test_a_thread_that_has_the_name_is_left_alone(stored, names):
    _lemon("Remote names")
    stored[_THREAD] = "Remote names (FilmyBoy)"

    thread_name.push(_THREAD)

    assert names == []


def test_a_session_that_is_not_a_lemon_keeps_codex_s_name(stored, names):
    with db.connect() as conn:
        db.add(conn, _CHANNEL, "Waiting", name="mine", metadata={"session_id": _THREAD})
    stored[_THREAD] = "Codex's own"

    thread_name.push(_THREAD)

    assert names == []


def test_a_thread_codex_does_not_know_is_not_named(names):
    _lemon("Remote names")

    thread_name.push(_THREAD)

    assert names == []


def test_the_service_names_an_idle_lemon_s_thread_after_reading_it(stored):
    _lemon("Remote names")
    stored[_THREAD] = "Accept Oria handoff brief"
    sets: list[tuple[str, str]] = []
    records = {
        _THREAD: codex_fakes.thread(_THREAD, name="Accept Oria handoff brief"),
        "01a1f6f1-0000-7000-8000-000000000002": None,
    }

    thread_name.catch_up(codex_fakes.server(stored, sets), records)
    assert sets == [(_THREAD, "Remote names (FilmyBoy)")]

    thread_name.catch_up(
        codex_fakes.server(stored, sets),
        {_THREAD: codex_fakes.thread(_THREAD, name=stored[_THREAD])},
    )
    assert len(sets) == 1
