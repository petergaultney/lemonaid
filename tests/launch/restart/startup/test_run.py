import dataclasses

from lemonaid.inbox import db
from lemonaid.launch.restart import startup, state
from lemonaid.messages import store

from .. import shared


def test_fresh_native_and_watcher_evidence_completes_same_row(tmp_path, monkeypatch):
    with db.connect() as conn:
        path, row, lemon_id, _transcript = shared.setup(conn, tmp_path)
        plan = {**shared.plan(tmp_path), "lemon_id": lemon_id}
        token = state.reserve(conn, plan)
        replacement = dataclasses.replace(shared.TARGET, pid=999)
        monkeypatch.setattr(startup.pane, "replace", lambda *args: replacement)
        monkeypatch.setattr(startup.pane, "restore", lambda *args: None)
        monkeypatch.setattr(startup.pane, "check", lambda target: target)
        monkeypatch.setattr(
            startup.process, "inspect", lambda pid: dataclasses.replace(shared.SOURCE, pid=pid)
        )
        monkeypatch.setattr(startup.watchers, "start", lambda *args: None)
        monkeypatch.setattr(startup, "ready", lambda *args: True)
        before = path.read_bytes()
        startup.run(conn, token)
        updated = db.get_by_channel(conn, shared.CHANNEL, unread_only=False)
        assert updated.id == row.id
        assert updated.name == row.name
        assert updated.status == row.status
        assert updated.created_at == row.created_at
        assert path.read_bytes() == before
        assert state.get(conn, token)["phase"] == "complete"
        pending = list(store.inbox_for_id(lemon_id).glob("*.md"))
        assert len(pending) == 1
        assert "continue your existing task" in pending[0].read_text()
