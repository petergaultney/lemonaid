import pytest

from lemonaid.inbox import db
from lemonaid.lemon_watchers import watcher


@pytest.fixture(autouse=True)
def _no_real_tmux(monkeypatch):
    """Point every un-stubbed `tmux` call at a socket that does not exist.

    Setters in tmux/scratch.py mirror state into tmux options, so a test that
    only meant to exercise a file write would otherwise set options on the
    developer's own server. Tests that want a server start their own and
    override this.
    """
    monkeypatch.setenv("TMUX", "/nonexistent/lemonaid-tests,0,0")


@pytest.fixture(autouse=True)
def _own_database(monkeypatch, tmp_path):
    """Every test gets an empty inbox of its own.

    Constructing a LemonaidApp starts its watcher, and a watcher reading the
    real inbox archived four live sessions the moment the tmux it could see was
    a test server with none of their ttys. It also made layout tests depend on
    whatever happened to be in the inbox at the time.
    """
    monkeypatch.setattr(db, "get_db_path", lambda: tmp_path / "lemonaid.db")


@pytest.fixture(autouse=True)
def _watchers_must_not_outlive_tests(_no_real_tmux, _own_database):
    """Fail safely if a test leaves the DB-mutating watcher behind.

    The cleanup runs before the database and TMUX monkeypatches are undone. A
    leaked watcher must never get a chance to observe the developer's real
    inbox while it still carries a test's fake view of tmux.
    """
    yield

    thread = watcher._watcher_thread
    if thread is not None and thread.is_alive():
        watcher.stop_unified_watcher()
        pytest.fail("test leaked the unified watcher thread")
