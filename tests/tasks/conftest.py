import pytest

from lemonaid.tasks.briefs import liveness


@pytest.fixture
def dead(monkeypatch) -> set[str]:
    """Lemon-IDs whose lemons aren't live; every other lemon is."""
    gone: set[str] = set()
    monkeypatch.setattr(liveness, "live", lambda _conn, lemon_id: lemon_id not in gone)
    return gone
