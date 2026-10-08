from lemonaid.watch import briefs_cli, briefs_events, delivery, waiter_lock

from .shared import args, open_watch, poll


def test_cli_once_and_self_resolution(family, monkeypatch, capsys):
    _, child, path, state_dir = family
    monkeypatch.setenv("LEMONAID_CHANNEL", "codex:parent")
    open_watch(family, me="")
    path.write_text(path.read_text().replace("working", "done"))
    assert briefs_cli.run(args(state_dir, "--self", "--once")) == 0
    assert f"{child}: Status: working -> done" in capsys.readouterr().out


def test_cli_status_and_duplicate_lock(family, capsys):
    parent, _, _, state_dir = family
    assert briefs_cli.run(args(state_dir, parent, "--status")) == 1
    state_dir.mkdir(exist_ok=True)
    path = briefs_events.state_stem(state_dir, parent, "").with_suffix(".lock")
    lock = waiter_lock.acquire(path)
    try:
        assert briefs_cli.run(args(state_dir, parent, "--status")) == 0
        assert briefs_cli.run(args(state_dir, parent, "--once")) == 3
        assert "already running" in capsys.readouterr().out
    finally:
        lock.close()


def test_cli_codex_delivery_is_one_shot_and_releases_lock(family, monkeypatch):
    parent, _, path, state_dir = family
    open_watch(family, me="")
    path.write_text(path.read_text().replace("working", "done"))
    monkeypatch.setenv("CODEX_THREAD_ID", "thread")
    monkeypatch.setattr(delivery, "codex_setup_problem", lambda: "")
    sent = []
    monkeypatch.setattr(
        delivery,
        "to_codex",
        lambda thread, kind, instruction: lambda message: sent.append((thread, kind, message)),
    )
    assert briefs_cli.run(args(state_dir, parent, "--codex-thread")) == 0
    assert sent[0][:2] == ("thread", "lemonaid watch briefs")
    assert not waiter_lock.held(
        briefs_events.state_stem(state_dir, parent, "").with_suffix(".lock")
    )
    assert poll(open_watch(family, me="")) == []


def test_cli_failed_delivery_does_not_consume_change(family, monkeypatch):
    parent, _, path, state_dir = family
    open_watch(family, me="")
    path.write_text(path.read_text().replace("working", "done"))
    monkeypatch.setattr(delivery, "codex_setup_problem", lambda: "")

    def fail(message):
        raise delivery.Failed("queue failed")

    monkeypatch.setattr(delivery, "to_codex", lambda *args: fail)
    assert briefs_cli.run(args(state_dir, parent, "--codex-thread", "thread")) == 1
    assert poll(open_watch(family, me=""))


def test_cli_refuses_unidentified_self(tmp_path, capsys):
    assert briefs_cli.run(args(tmp_path, "--self", "--once")) == 2
    assert "Cannot identify" in capsys.readouterr().out
