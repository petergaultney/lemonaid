"""`lemon archived` lists attic briefs and says which `tell --wake` could bring back."""

import time

import pytest

from lemonaid.brief import archive, attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.messages import archived_cli
from lemonaid.restore import plan


@pytest.fixture(autouse=True)
def _transcripts(monkeypatch):
    monkeypatch.setattr(plan, "transcript_missing", lambda row: row.channel == "claude:lost")


def _archived(name: str, channel: str, tmp_path) -> str:
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: done\n\n## Now\n\n| a | b |\n\n- {name} finished\n")
    with db.connect() as conn:
        lemon_id = identity.ensure(conn, path)
        if channel:
            db.add(conn, channel, "", metadata={"cwd": str(tmp_path)}, switch_source="tmux")
            attached.attach(conn, channel, path)
        archive.archive(conn, path, time.time(), {channel}, why="test")
    return lemon_id


def test_each_archived_lemon_says_whether_it_can_be_woken(tmp_path):
    kept = _archived("kept", "claude:kept", tmp_path)
    lost = _archived("lost", "claude:lost", tmp_path)
    unrecorded = _archived("unrecorded", "", tmp_path)

    with db.connect() as conn:
        found = {each.lemon_id: each for each in archived_cli.archived(conn, 0, Config())}

    assert found[kept].why_not == ""
    assert found[kept].now == "kept finished"
    assert found[kept].status == "done"
    assert found[lost].why_not.startswith("its conversation's transcript is gone")
    assert found[unrecorded].why_not == "no session was recorded for it"


def test_briefs_changed_before_since_are_left_out(tmp_path):
    _archived("old", "claude:kept", tmp_path)

    with db.connect() as conn:
        assert archived_cli.archived(conn, time.time() + 60, Config()) == []


def test_a_session_holding_another_brief_now_cannot_be_woken(tmp_path):
    lemon_id = _archived("moved-on", "claude:kept", tmp_path)
    newer = brief_store.briefs_dir() / "newer.md"
    newer.write_text("# newer\n\nStatus: working\n")
    with db.connect() as conn:
        attached.attach(conn, "claude:kept", newer)
        [found] = archived_cli.archived(conn, 0, Config())

    assert found.lemon_id == lemon_id
    assert "has another brief attached now (newer.md)" in found.why_not
