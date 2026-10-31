from lemonaid.brief import identity
from lemonaid.inbox import db
from lemonaid.tasks.briefs import session
from lemonaid.tasks.model import holding, ledger

from ..shared import new_task


def _brief(tmp_path, lemon_id):
    path = tmp_path / "briefs" / "2026-10-31-work.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Work\n\nLemon-ID: {lemon_id}\n")
    with db.connect() as conn:
        identity.ensure(conn, path)
    return path


def test_first_start_starts_the_clock_and_lists_the_acknowledge_command(tmp_path):
    path = _brief(tmp_path, "work.Alpha")
    with db.connect() as conn:
        task = new_task(conn, brief_id="work.Alpha")
        text = session.started(conn, path, 500.0)
        resumed = session.started(conn, path, 900.0)

        assert ledger.state(conn, task)["attached_at"] == 500.0
        assert f"lemonaid task acknowledge {task}" in text
        assert resumed == text

        with ledger.transaction(conn):
            holding.acknowledge(conn, task, 2, "work.Alpha", "ack", 950.0)
        assert "acknowledge " not in session.started(conn, path, 999.0).split("\n", 1)[1]


def test_no_tasks_and_task_support_off_add_nothing(tmp_path):
    path = _brief(tmp_path, "work.Alpha")
    with db.connect() as conn:
        assert session.started(conn, path, 1.0) == ""
        new_task(conn, brief_id="work.Alpha")
        assert session.context(conn, path, enabled=False) == ""
