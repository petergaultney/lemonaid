import asyncio
import threading

from lemonaid.config import PlaceRoot
from lemonaid.inbox.tui import project_names


def test_pending_success_and_failures_are_looked_up_once_off_thread(tmp_path, monkeypatch):
    root = PlaceRoot(tmp_path, project_name="hook {dir}")
    cache = project_names.Cache()
    calls = []
    changes = []
    ui_thread = threading.get_ident()

    def resolve(root, directory):
        assert threading.get_ident() != ui_thread
        calls.append(directory)
        return "project" if directory.endswith("one") else ""

    monkeypatch.setattr(project_names, "resolve", resolve)
    assert cache.request("one", root)
    assert not cache.request("one", root)
    assert not cache.request("two", root)
    assert cache.names == {"one": "", "two": ""}
    asyncio.run(cache.drain(lambda: changes.append(dict(cache.names))))
    assert calls == ["one", "two"]
    assert cache.names == {"one": "project", "two": ""}
    assert len(changes) == 1
    assert not cache.request("two", root)
    assert cache.request("three", root)
    asyncio.run(cache.drain(lambda: None))
    assert calls == ["one", "two", "three"]


def test_hookless_and_unknown_roots_do_not_schedule(tmp_path):
    cache = project_names.Cache()
    assert not cache.request("", PlaceRoot(tmp_path, project_name="hook"))
    assert not cache.request("one", None)
    assert not cache.request("two", PlaceRoot(tmp_path))
    assert cache.names == {}
