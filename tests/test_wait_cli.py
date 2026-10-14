import argparse
import threading

from lemonaid.brief import attached, store
from lemonaid.inbox import db
from lemonaid.messages import store as messages
from lemonaid.watch import batch_wait, cli, delivery, wait_cli, wait_state, waiter_lock


def test_wait_is_registered_holds_one_lock_and_delivers_inbox(monkeypatch, capsys):
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text("# task\n\nBrief-ID: task.IndexElf\n\n## Watching\n")
    with db.connect() as conn:
        db.add(conn, "codex:test", "", metadata={})
        attached.attach(conn, "codex:test", path)
    inbox = messages.inbox_for_id("task.IndexElf")
    messages.send(inbox, "one message", "other.IndexElf")
    args = argparse.Namespace(
        codex_thread="", channel="codex:test", status=False, interval=0.01, quiet=0, push=False
    )
    real_wait = batch_wait.wait

    def wait(*positional, **keywords):
        assert wait_state.is_armed("task.IndexElf")
        assert waiter_lock.acquire(wait_state.lock_path("task.IndexElf"), grace=0) is None
        real_wait(*positional, **keywords)

    monkeypatch.setattr(batch_wait, "wait", wait)
    assert wait_cli.run(args) == 0
    assert "one message" in capsys.readouterr().out
    assert not wait_state.is_armed("task.IndexElf")


def test_an_archived_session_stops_watching_its_brief():
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text("# task\n\nBrief-ID: task.IndexElf\n")
    with db.connect() as conn:
        db.add(conn, "codex:test", "", metadata={})
        attached.attach(conn, "codex:test", path)
        conn.execute("UPDATE notifications SET status = 'archived' WHERE channel = 'codex:test'")
        conn.commit()
    args = argparse.Namespace(
        codex_thread="", channel="codex:test", status=False, interval=0.01, quiet=0, push=False
    )
    assert wait_cli.run(args) == 0
    assert not wait_state.is_armed("task.IndexElf")


def test_codex_rearm_waits_for_an_old_waiter_that_is_delivering(monkeypatch):
    path = store.briefs_dir() / "task.md"
    path.parent.mkdir(parents=True)
    path.write_text("# task\n\nBrief-ID: task.IndexElf\n\n## Watching\n")
    with db.connect() as conn:
        db.add(conn, "codex:test", "", metadata={})
        attached.attach(conn, "codex:test", path)
    args = argparse.Namespace(
        codex_thread="test", channel="", status=False, interval=0.01, quiet=0, push=False
    )
    releasing, next_armed, stop_next = threading.Event(), threading.Event(), threading.Event()
    runs, results, threads = [], [], []
    monkeypatch.setattr(delivery, "codex_setup_problem", lambda: "")

    def queue(message):
        assert wait_state.delivering("task.IndexElf")
        thread = threading.Thread(target=lambda: results.append(wait_cli.run(args)))
        threads.append(thread)
        thread.start()
        threading.Timer(0.15, releasing.set).start()

    monkeypatch.setattr(delivery, "to_codex", lambda *args: queue)

    def wait(*args, **kwargs):
        runs.append(True)
        if len(runs) == 1:
            args[4]("one batch")
            assert releasing.wait(5)
        else:
            next_armed.set()
            stop_next.wait(5)

    monkeypatch.setattr(batch_wait, "wait", wait)
    try:
        assert wait_cli.run(args) == 0
        assert next_armed.wait(5)
        assert wait_state.is_armed("task.IndexElf")
    finally:
        releasing.set()
        stop_next.set()
        for thread in threads:
            thread.join(5)
    assert results == [0]


def test_watch_self_and_wait_alias_use_the_same_backend(monkeypatch):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    cli.setup_parser(commands)
    wait_cli.setup_parser(commands)
    calls = []
    monkeypatch.setattr(wait_cli, "run", lambda args: calls.append(args) or 0)
    for command in ["watch", "wait"]:
        args = parser.parse_args([command, "--self", "--status"])
        try:
            args.func(args)
        except SystemExit as error:
            assert error.code == 0
    assert len(calls) == 2
    assert all(args.use_self and args.status for args in calls)
    single = parser.parse_args(["watch", "doc", "--wait", "/tmp/review.md"])
    assert single.func is not wait_cli._cmd
