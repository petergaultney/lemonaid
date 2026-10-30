"""Detached recovery never substitutes an alias for the actual queue target."""

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db
from lemonaid.messages import recipient
from lemonaid.watch import codex_waiter, scout_roster, scout_start, wait_state, waiter_lock


def test_ensure_registers_the_real_thread_with_the_host(monkeypatch):
    spawned = []
    monkeypatch.setattr(scout_start, "_spawn", lambda: spawned.append(True))

    assert not codex_waiter.ensure("codex:alias", "root", "task.IndexElf")

    registration = scout_roster.read("task.IndexElf")
    assert registration and (registration.channel, registration.thread) == ("codex:alias", "root")
    assert spawned == [True]


def test_recovery_launch_is_serialized_and_existing_waiter_is_kept(monkeypatch):
    armed = False
    calls = []
    monkeypatch.setattr(wait_state, "is_armed", lambda *args, **kwargs: armed)

    def host(lemon_id, channel, thread, cwd):
        nonlocal armed
        assert waiter_lock.held(wait_state.lock_path(lemon_id).with_suffix(".start.lock"))
        assert not codex_waiter.ensure(channel, thread, lemon_id)
        calls.append((channel, thread))
        armed = True

    monkeypatch.setattr(scout_start, "host", host)
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


def test_restore_skips_a_done_brief_and_names_the_lemons_it_started(monkeypatch):
    ids = {}
    for name, state in (("lead", "working"), ("finished", "done")):
        path = brief_store.briefs_dir() / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n\nStatus: {state}\n")
        with db.connect() as conn:
            db.add(conn, f"codex:{name}", "", metadata={"tty": f"/dev/{name}"})
            attached.attach(conn, f"codex:{name}", path)
            ids[name] = identity.ensure(conn, path)
    started = []
    monkeypatch.setattr(codex_waiter.utils, "find_session_path", lambda thread: "rollout.jsonl")
    monkeypatch.setattr(recipient, "harness_alive", lambda row: True)
    monkeypatch.setattr(codex_waiter, "_restored", {})
    monkeypatch.setattr(codex_waiter, "ensure", lambda *args: started.append(args[0]) or True)

    with db.connect() as conn:
        named = codex_waiter.restore(conn, {"lead": {"/dev/lead"}, "finished": {"/dev/finished"}})

    assert started == ["codex:lead"]
    assert named == codex_waiter.Restored([ids["lead"]], False)


def test_restore_that_cannot_list_codex_processes_is_unsettled(monkeypatch):
    monkeypatch.setattr(codex_waiter.processes, "thread_ttys", lambda: None)

    with db.connect() as conn:
        assert codex_waiter.restore(conn) == codex_waiter.Restored([], True)
