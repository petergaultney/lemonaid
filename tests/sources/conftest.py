import pytest

from lemonaid.plugins import processes
from lemonaid.sources import host


@pytest.fixture(autouse=True)
def fake_source_dir(tmp_path, monkeypatch):
    home = tmp_path / "fake-source"
    home.mkdir()
    monkeypatch.setenv("FAKE_SOURCE_DIR", str(home))
    processes.close()
    processes._failed_at.clear()
    host.check.cache_clear()
    yield home
    processes.close()
    processes._failed_at.clear()
    host._ready.clear()
    host.check.cache_clear()
