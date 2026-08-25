import pytest

from lemonaid.inbox import db


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
