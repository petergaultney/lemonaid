"""Detached recovery never substitutes an alias for the actual queue target."""

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db
from lemonaid.messages import recipient
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
    assert {"--push", "--foreground"} <= set(args[0])
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


def test_restore_tries_each_lemon_at_most_once_a_minute(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(codex_waiter.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(codex_waiter, "_restored", {})

    assert codex_waiter._due("task.IndexElf")
    assert not codex_waiter._due("task.IndexElf")
    assert codex_waiter._due("other.IndexElf")
    clock[0] += codex_waiter.RETRY_SECONDS
    assert codex_waiter._due("task.IndexElf")


def test_restore_starts_a_scout_for_a_brief_with_nothing_to_watch(monkeypatch):
    path = brief_store.briefs_dir() / "lead.md"
    path.parent.mkdir(parents=True)
    path.write_text("# lead\n\nStatus: working\n")
    with db.connect() as conn:
        db.add(conn, "codex:root", "", metadata={"tty": "/dev/ttys001"})
        attached.attach(conn, "codex:root", path)
        lemon_id = identity.ensure(conn, path)
    started = []
    monkeypatch.setattr(codex_waiter.utils, "find_session_path", lambda thread: "rollout.jsonl")
    monkeypatch.setattr(recipient, "harness_alive", lambda row: True)
    monkeypatch.setattr(codex_waiter, "_restored", {})
    monkeypatch.setattr(codex_waiter, "ensure", lambda *args: started.append(args))

    with db.connect() as conn:
        codex_waiter.restore(conn, {"root": {"/dev/ttys001"}})

    assert started == [("codex:root", "root", lemon_id)]
