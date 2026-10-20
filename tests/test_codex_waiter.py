"""Detached recovery never substitutes an alias for the actual queue target."""

from lemonaid.inbox import db
from lemonaid.watch import codex_waiter, wait_state, waiter_lock

_SPAWN = codex_waiter._spawn


def test_spawn_passes_real_thread_and_isolated_database(monkeypatch):
    calls = []
    monkeypatch.setattr(
        codex_waiter.subprocess, "Popen", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    _SPAWN("codex:alias", "root")
    args, kwargs = calls[0]
    assert args[0][-2:] == ["--codex-thread", "root"]
    assert kwargs["env"]["CODEX_THREAD_ID"] == "root"
    assert kwargs["env"]["LEMONAID_CHANNEL"] == "codex:alias"
    assert kwargs["env"]["LEMONAID_DB"] == str(db.get_db_path())
    assert kwargs["start_new_session"]


def test_recovery_launch_is_serialized_and_existing_waiter_is_kept(monkeypatch):
    armed = False
    calls = []
    monkeypatch.setattr(wait_state, "is_armed", lambda *args, **kwargs: armed)

    def spawn(channel, thread):
        nonlocal armed
        assert waiter_lock.held(wait_state.lock_path("task.IndexElf").with_suffix(".start.lock"))
        assert not codex_waiter.ensure(channel, thread, "task.IndexElf")
        calls.append((channel, thread))
        armed = True

    monkeypatch.setattr(codex_waiter, "_spawn", spawn)
    assert codex_waiter.ensure("codex:alias", "root", "task.IndexElf")
    assert codex_waiter.ensure("codex:alias", "root", "task.IndexElf")
    assert calls == [("codex:alias", "root")]
