"""Where the inbox file lives.

`LEMONAID_DB` is what makes a second `lma` against invented sessions safe: the
demo script and any experiment get their own database, so neither inbox's
watchers can archive the other's rows.
"""

from pathlib import Path

from lemonaid.inbox import db

# conftest's autouse fixture replaces get_db_path outright, and that is the
# function under test - so these call the original rather than the stand-in.
_real_get_db_path = db.get_db_path


def test_the_default_is_the_xdg_path(monkeypatch):
    monkeypatch.delenv("LEMONAID_DB", raising=False)

    assert _real_get_db_path() == Path.home() / ".local" / "share" / "lemonaid" / "lemonaid.db"


def test_an_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("LEMONAID_DB", str(tmp_path / "demo.db"))

    assert _real_get_db_path() == tmp_path / "demo.db"


def test_an_empty_override_is_not_an_override(monkeypatch):
    """An unset-but-exported variable must not point the inbox at the cwd."""
    monkeypatch.setenv("LEMONAID_DB", "")

    assert _real_get_db_path().name == "lemonaid.db"


def test_an_override_creates_the_directory_it_names(monkeypatch, tmp_path):
    """The caller passes a path, not a path whose parent they had to make."""
    monkeypatch.setenv("LEMONAID_DB", str(tmp_path / "nested" / "demo.db"))

    assert _real_get_db_path().parent.is_dir()


def test_a_tilde_override_expands(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LEMONAID_DB", "~/demo.db")

    assert _real_get_db_path() == tmp_path / "demo.db"
