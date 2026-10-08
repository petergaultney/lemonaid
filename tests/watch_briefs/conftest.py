import pytest

from .shared import lemon, link


@pytest.fixture
def family(tmp_path):
    parent, _ = lemon("parent", channel="codex:parent")
    child, path = lemon("child")
    link(child, parent)
    return parent, child, path, tmp_path / "watch-state"
