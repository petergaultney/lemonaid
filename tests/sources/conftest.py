import pytest

from lemonaid.sources import host


@pytest.fixture(autouse=True)
def fake_source_dir(tmp_path, monkeypatch):
    home = tmp_path / "fake-source"
    home.mkdir()
    monkeypatch.setenv("FAKE_SOURCE_DIR", str(home))
    host.close()
    host._host.failed_at.clear()
    host.check.cache_clear()
    yield home
    host.close()
    host._host.failed_at.clear()
    host._host.ready.clear()
    host.check.cache_clear()
