import pytest


@pytest.fixture(autouse=True)
def _homes(monkeypatch, tmp_path):
    """An old and a new home of the test's own, with no single-folder overrides."""
    monkeypatch.delenv("LEMONAID_BRIEFS_DIR", raising=False)
    monkeypatch.delenv("LEMONAID_MESSAGES_DIR", raising=False)
    monkeypatch.setenv("LEMONAID_LEMONS_DIR", str(tmp_path / "lemons"))
    monkeypatch.setenv("LEMONAID_LEGACY_BRIEFS_DIR", str(tmp_path / "brief-lemons"))
    for name in ("LEMONAID_CHANNEL", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX_PANE"):
        monkeypatch.delenv(name, raising=False)
