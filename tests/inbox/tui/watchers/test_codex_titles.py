import json
from pathlib import Path

import pytest

from lemonaid.codex import titles
from lemonaid.inbox import db
from lemonaid.inbox.tui.watchers import session_names


@pytest.fixture
def codex_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    monkeypatch.setenv("LEMONAID_DB", str(tmp_path / "l.db"))
    return tmp_path


def _write_index(home: Path, *entries: tuple[str, str]) -> None:
    (home / "session_index.jsonl").write_text(
        "".join(json.dumps({"id": i, "thread_name": t}) + "\n" for i, t in entries)
    )


def _add(name: str, session_id: str = "abc", channel: str = "") -> None:
    with db.connect() as conn:
        db.add(
            conn,
            channel or f"codex:{session_id}",
            "hi",
            name=name,
            metadata={"session_id": session_id, "name_source": "environment"},
        )


def _name() -> str:
    with db.connect() as conn:
        return db.get_active(conn, switch_source=None)[0].name


def test_placeholder_name_becomes_the_latest_index_title(codex_home: Path) -> None:
    _add("spatial-lemon-jump")
    _write_index(codex_home, ("abc", "old"), ("abc", "Review #418 grove"))

    assert session_names.upgrade({}, titles.IndexCache()) is True
    assert _name() == "Review #418 grove"


def test_generic_titles_are_ignored(codex_home: Path) -> None:
    _add("spatial-lemon-jump")
    _write_index(codex_home, ("abc", "Guardian review"))

    assert session_names.upgrade({}, titles.IndexCache()) is False
    assert _name() == "spatial-lemon-jump"


def test_a_user_rename_stays_visible(codex_home: Path) -> None:
    _add("spatial-lemon-jump")
    with db.connect() as conn:
        db.update_name(conn, db.get_active(conn, switch_source=None)[0].id, "mine")
    _write_index(codex_home, ("abc", "Codex title"))

    session_names.upgrade({}, titles.IndexCache())
    assert _name() == "mine"


def test_a_row_added_after_the_index_scan_still_gets_its_title(codex_home: Path) -> None:
    _write_index(codex_home, ("abc", "Title"))
    cache = titles.IndexCache()
    session_names.upgrade({}, cache)
    _add("spatial-lemon-jump")

    assert session_names.upgrade({}, cache) is True
    assert _name() == "Title"


def test_a_reconciled_row_is_titled_by_its_session_id(codex_home: Path) -> None:
    _add("spatial-lemon-jump", session_id="abc", channel="codex:transient")
    _write_index(codex_home, ("abc", "Title"))

    session_names.upgrade({}, titles.IndexCache())
    assert _name() == "Title"
