from lemonaid.inbox.tui import usage_view
from lemonaid.usage import samples


def test_unreadable_usage_reads_as_empty(monkeypatch):
    def boom() -> dict:
        raise ValueError("corrupt")

    monkeypatch.setattr(samples, "current_samples", boom)

    assert usage_view.read_samples() == {}
