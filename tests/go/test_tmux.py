import pytest

from lemonaid import go

from .shared import run
from .shared_tmux import _query, _record


def test_jump_selects_target_pane(server, clients):
    _query(server, "new-session", "-d", "-s", "target")
    _query(server, "split-window", "-d", "-t", "target")
    found = _record(server, "target:0.1")
    clients("source")
    run("codex:real")
    assert (
        _query(server, "list-clients", "-F", "#{pane_id}")
        == found.metadata["tmux_pane_identity"][0]
    )


def test_replacement_pane_is_rejected(server):
    _query(server, "split-window", "-d", "-t", "source")
    found = _record(server, "source:0.1")
    old_pane = found.metadata["tmux_pane_identity"][0]
    _query(server, "kill-pane", "-t", old_pane)
    _query(server, "split-window", "-d", "-t", "source")
    replacement = _query(server, "display-message", "-p", "-t", "source:0.1", "#{pane_id}")
    assert replacement != old_pane
    with pytest.raises(LookupError, match="gone or ambiguous"):
        go._pane(server, found)


def test_duplicate_window_links_resolve_one_pane(server):
    found = _record(server, "source:0")
    _query(server, "link-window", "-s", "source:0", "-t", "source:1")
    assert go._pane(server, found) == found.metadata["tmux_pane_identity"][0]


def test_shared_source_window_requires_explicit_client(server, clients):
    source_pane = _query(server, "display-message", "-p", "-t", "source", "#{pane_id}")
    _query(server, "new-session", "-d", "-s", "second")
    _query(server, "link-window", "-s", "source:0", "-t", "second:1")
    clients("source")
    clients("second")
    _query(server, "select-window", "-t", "second:1")
    with pytest.raises(LookupError, match="Use --client"):
        go._client(server, "", source_pane)
    explicit = _query(server, "list-clients", "-F", "#{client_name}").splitlines()[0]
    assert go._client(server, explicit, source_pane) == explicit


def test_inbox_jump_without_tty_returns_to_author_from_reviewer(server, clients, monkeypatch):
    from lemonaid import handlers
    from lemonaid.config import Config

    author = _record(server, "source:0")
    pane = author.metadata["tmux_pane_identity"][0]
    reviewer = _query(server, "new-window", "-P", "-F", "#{pane_id}", "-t", "source")
    clients("source")
    assert _query(server, "list-clients", "-F", "#{pane_id}") == reviewer
    monkeypatch.setenv("TMUX", f"{server[2]},0,0")
    metadata = {k: v for k, v in author.metadata.items() if k != "tty"}

    assert handlers.handle_notification(metadata, Config(), switch_source="tmux")
    assert _query(server, "list-clients", "-F", "#{pane_id}") == pane


def test_background_repair_precedes_author_click(server, clients, monkeypatch):
    from lemonaid import handlers
    from lemonaid.codex import processes
    from lemonaid.config import Config
    from lemonaid.inbox import db

    author = _record(server, "source:0")
    _query(server, "new-window", "-t", "source")
    reviewer = _record(server, "source:1")
    with db.connect() as conn:
        db.add(conn, "codex:author", "author", metadata=reviewer.metadata, switch_source="tmux")
    clients("source")
    monkeypatch.setenv("TMUX", f"{server[2]},0,0")
    monkeypatch.setattr(processes, "thread_ttys", lambda: {"author": {author.metadata["tty"]}})

    with db.connect() as conn:
        assert handlers.repair_tmux_locations(conn) == 1
        fixed = db.get_by_channel(conn, "codex:author", unread_only=False)
    monkeypatch.setattr(processes, "thread_ttys", lambda: pytest.fail("click must not scan"))
    assert handlers.handle_notification(
        {**fixed.metadata, "channel": "codex:author"}, Config(), switch_source="tmux"
    )
    assert (
        _query(server, "list-clients", "-F", "#{pane_id}")
        == author.metadata["tmux_pane_identity"][0]
    )
    with db.connect() as conn:
        fixed = db.get_by_channel(conn, "codex:author", unread_only=False)
        assert fixed.metadata["tty"] == author.metadata["tty"]
        assert fixed.metadata["tmux_window"] == "0"
        assert fixed.metadata["tmux_pane_identity"] == author.metadata["tmux_pane_identity"]


@pytest.mark.parametrize("destination", ["source:1", "second:1"])
def test_linked_physical_pane_with_verified_owner_remains_switchable(
    server, clients, monkeypatch, destination
):
    from lemonaid import handlers
    from lemonaid.codex import processes
    from lemonaid.config import Config
    from lemonaid.inbox import db

    row = _record(server, "source:0")
    if destination.startswith("second:"):
        _query(server, "new-session", "-d", "-s", "second")
    _query(server, "link-window", "-s", "source:0", "-t", destination)
    reviewer = _query(server, "new-window", "-P", "-F", "#{pane_id}", "-t", "source")
    clients("source")
    assert _query(server, "list-clients", "-F", "#{pane_id}") == reviewer
    monkeypatch.setenv("TMUX", f"{server[2]},0,0")
    monkeypatch.setattr(processes, "thread_ttys", lambda: {"real": {row.metadata["tty"]}})
    assert len(handlers.codex_tmux_locations()["real"]) == 1
    with db.connect() as conn:
        assert handlers.repair_tmux_locations(conn) == 1
        row = db.get(conn, row.id)
    assert handlers.handle_notification(
        {**row.metadata, "channel": row.channel}, Config(), switch_source="tmux"
    )
    assert (
        _query(server, "list-clients", "-F", "#{pane_id}") == row.metadata["tmux_pane_identity"][0]
    )
    with db.connect() as conn:
        assert handlers.repair_tmux_locations(conn) == 0


def test_codex_click_uses_only_tmux_and_never_repairs_db(server, clients, monkeypatch):
    import subprocess

    from lemonaid import handlers
    from lemonaid.config import Config
    from lemonaid.inbox import db
    from lemonaid.inbox.tui.watchers import focus

    row = _record(server, "source:0")
    target = row.metadata["tmux_pane_identity"][0]
    _query(server, "new-window", "-t", "source")
    clients("source")
    monkeypatch.setenv("TMUX", f"{server[2]},0,0")
    run = subprocess.run
    calls = []

    def tmux_only(argv, **kwargs):
        assert argv[0] == "tmux", f"unexpected click subprocess: {argv}"
        calls.append(argv)
        return run(argv, **kwargs)

    def no_db(*args, **kwargs):
        pytest.fail("switch handler must not open or repair the inbox database")

    with monkeypatch.context() as click:
        click.setattr(subprocess, "run", tmux_only)
        click.setattr(db, "connect", no_db)
        click.setattr(handlers, "codex_tmux_locations", no_db)
        assert not focus.is_behind_scratch(row, target)
        assert handlers.handle_notification(
            {**row.metadata, "channel": row.channel}, Config(), switch_source="tmux"
        )
    assert calls
    assert _query(server, "list-clients", "-F", "#{pane_id}") == target


def test_codex_row_activation_switches_recorded_pane(server, clients, monkeypatch):
    import asyncio

    from textual.widgets.data_table import RowKey

    from lemonaid.inbox.tui.app import LemonaidApp
    from lemonaid.inbox.tui.watchers import watcher_hooks

    row = _record(server, "source:0")
    target = row.metadata["tmux_pane_identity"][0]
    other = _query(server, "new-window", "-P", "-F", "#{pane_id}", "-t", "source")
    clients("source")
    monkeypatch.setenv("TMUX", f"{server[2]},0,0")
    monkeypatch.setattr(watcher_hooks, "start", lambda *args, **kwargs: None)
    monkeypatch.setattr("lemonaid.inbox.tui.app.detect_terminal_switch_source", lambda: "tmux")

    async def measure():
        app = LemonaidApp()
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause()
            _query(server, "switch-client", "-t", other)
            app._activate_row("main_table", RowKey(str(row.id)))
            assert _query(server, "list-clients", "-F", "#{pane_id}") == target

    asyncio.run(measure())
