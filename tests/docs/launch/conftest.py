import pytest

from lemonaid.docs import lemons

from ..shared import configure, doc


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    doc(root, "packages/core.md", {"package-for": [{}]})
    doc(root, "packages/oria.md", {"package-for": [{"group": "oria"}]})
    doc(root, "voice.md", {"package": "core"}, "Write plainly.\n")
    doc(root, "flaky.md", {"package": "oria"}, "Chase flaky tests.\n")
    (tmp_path / "classic.md").write_text("@chain.md\n")
    configure([root], f'classic = "{tmp_path / "classic.md"}"\n')
    monkeypatch.setattr(lemons, "kin", lambda lemon_id: ((), ()))
    return root
