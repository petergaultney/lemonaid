from lemonaid.brief import attached, identity
from lemonaid.inbox import db
from lemonaid.tasks.briefs import session
from lemonaid.tasks.model import ledger

from ..shared import new_task


def _brief(tmp_path, lemon_id):
    path = tmp_path / "briefs" / "2026-10-31-work.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Work\n\nLemon-ID: {lemon_id}\n")
    with db.connect() as conn:
        identity.ensure(conn, path)
    return path


def test_first_start_records_the_start_and_lists_the_tasks(tmp_path):
    path = _brief(tmp_path, "work.Alpha")
    with db.connect() as conn:
        task = new_task(conn, brief_id="work.Alpha")
        text = session.started(conn, path, 500.0)
        resumed = session.started(conn, path, 900.0)

        assert ledger.state(conn, task)["attached_at"] == 500.0
        assert f"- task:{task} (Do the work)" in text and "task assign" in text
        assert resumed == text


def test_no_tasks_and_task_support_off_add_nothing(tmp_path):
    path = _brief(tmp_path, "work.Alpha")
    with db.connect() as conn:
        assert session.started(conn, path, 1.0) == ""
        new_task(conn, brief_id="work.Alpha")
        assert session.context(conn, path, enabled=False) == ""


def test_a_brief_attached_after_its_session_started_is_caught_up(tmp_path):
    path = _brief(tmp_path, "work.Alpha")
    with db.connect() as conn:
        waiting = new_task(conn, brief_id="work.Alpha")
        assigned_later = new_task(conn, brief_id="work.Alpha", request_id="late", at=4e9)
        unattached = new_task(conn, brief_id="other.Beta", request_id="other")
        attached.attach(conn, "tmux:work:1", path)
        since = conn.execute("SELECT attached_at FROM session_briefs").fetchone()[0]

        assert sorted(session.caught_up(conn)) == sorted([waiting, assigned_later])
        assert ledger.state(conn, waiting)["attached_at"] == since
        assert ledger.state(conn, assigned_later)["attached_at"] == 4e9
        assert ledger.state(conn, unattached)["attached_at"] is None
        assert session.caught_up(conn) == []
