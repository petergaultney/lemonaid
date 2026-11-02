from lemonaid.inbox import db
from lemonaid.tasks.model import holding, ledger, tree

from ..shared import new_task


def _family(conn):
    conn.executemany(
        "INSERT INTO lemon_parents (lemon_id, parent_id, linked_at) VALUES (?, ?, 0)",
        [("Child.one", "Lead.lead"), ("Grand.kid", "Child.one"), ("Other.lead", "Hq.hq")],
    )
    conn.commit()


def _assign(conn, task, to):
    with ledger.transaction(conn):
        revision = ledger.state(conn, task)["revision"]
        holding.assign(conn, task, revision, to, "", True, "x", f"{task}-{to}", 1.0)


def _listed(conn, brief="Lead.lead", include_closed=False):
    return {
        r["task_id"]: [(c["brief_id"], c["kind"]) for c in r["connections"]]
        for r in tree.rows(conn, brief, include_closed)
    }


def test_tree_lists_descendant_work_incoming_transfers_and_work_held_outside():
    with db.connect() as conn:
        _family(conn)
        grandchild = new_task(conn, brief_id="Grand.kid", sponsor="Child.one")
        incoming = new_task(conn, brief_id="Other.work", sponsor="Other.lead")
        _assign(conn, incoming, "brief:Child.one")
        reviewed = new_task(conn, brief_id="Child.one", request_id="c1")
        _assign(conn, reviewed, "brief:Outside.reviewer")
        unrelated = new_task(conn, brief_id="Other.lead", sponsor="Hq.hq")

        listed = _listed(conn)

        assert listed == {
            grandchild: [("Grand.kid", "holder"), ("Grand.kid", "spec")],
            incoming: [("Child.one", "holder")],
            reviewed: [("Child.one", "spec")],
        }
        assert unrelated not in _listed(conn, "Child.one")


def test_a_task_transferred_out_of_the_tree_is_no_longer_a_member():
    with db.connect() as conn:
        _family(conn)
        visiting = new_task(conn, brief_id="Other.work", sponsor="Other.lead")
        _assign(conn, visiting, "brief:Child.one")
        _assign(conn, visiting, "brief:Other.work")

        assert visiting not in _listed(conn)


def test_rerolled_ids_resolve_and_closed_tasks_need_include_closed():
    with db.connect() as conn:
        _family(conn)
        old = new_task(conn, brief_id="Old.name", sponsor="Lead.lead")
        conn.execute(
            "INSERT INTO lemon_aliases (old_id, lemon_id) VALUES ('Old.name', 'Grand.kid')"
        )
        conn.commit()
        assert _listed(conn)[old] == [("Grand.kid", "holder"), ("Grand.kid", "spec")]

        conn.execute("UPDATE tasks SET lifecycle = 'closed' WHERE task_id = ?", (old,))
        assert old not in _listed(conn)
        assert old in _listed(conn, include_closed=True)
        assert old in _listed(conn, brief="Old.name", include_closed=True)
