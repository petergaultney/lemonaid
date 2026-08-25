import pytest


@pytest.fixture(autouse=True)
def _no_real_tmux(monkeypatch):
    """Point every un-stubbed `tmux` call at a socket that does not exist.

    Setters in tmux/scratch.py mirror state into tmux options, so a test that
    only meant to exercise a file write would otherwise set options on the
    developer's own server. Tests that want a server start their own and
    override this.
    """
    monkeypatch.setenv("TMUX", "/nonexistent/lemonaid-tests,0,0")
