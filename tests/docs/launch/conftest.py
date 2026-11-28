import pytest

from lemonaid.docs import lemons

from ..shared import configure, doc


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    doc(root, "packages/core.md", {"package-for": [{}]})
    doc(root, "packages/webapp.md", {"package-for": [{"group": "webapp"}]})
    doc(root, "voice.md", {"package": "core"}, "Write plainly.\n")
    doc(root, "flaky.md", {"package": "webapp"}, "Chase flaky tests.\n")
    (tmp_path / "classic.md").write_text("@chain.md\n")
    configure([root], f'classic = "{tmp_path / "classic.md"}"\n')
    monkeypatch.setattr(lemons, "kin", lambda lemon_id: ((), ()))
    return root
