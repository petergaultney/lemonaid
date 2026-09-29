"""An undone monkeypatch must never leave a test pointed at the developer's real state."""

from pathlib import Path

from lemonaid.brief import store
from lemonaid.home import layout
from lemonaid.inbox import db


def test_undoing_every_patch_still_leaves_the_database_and_homes_private(monkeypatch):
    monkeypatch.undo()
    real = Path.home()

    assert not db.get_db_path().is_relative_to(real / ".local")
    assert not layout.lemons_dir().is_relative_to(real / ".lemons")
    assert not layout.legacy_dir().is_relative_to(real / ".brief-lemons")
    assert not store.briefs_dir().is_relative_to(real / ".brief-lemons")
