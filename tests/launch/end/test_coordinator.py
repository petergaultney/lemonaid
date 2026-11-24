"""Ending a lemon whose harness has already exited: its card, waiters and brief."""

from lemonaid.audit import events
from lemonaid.brief import archive, child_place, children, lemon
from lemonaid.config import Config
from lemonaid.inbox import db, ended
from lemonaid.launch.end import coordinator, plan
from lemonaid.launch.restart import state

from . import shared


def _end(target: str, by: str) -> list[str]:
    with db.connect() as conn:
        return coordinator.run(plan.build(conn, target, Config(), by=by))


def test_its_brief_goes_to_the_attic_and_its_parent_stops_listing_it():
    lead, _ = shared.lemon("lead", channel="claude:lead")
    reviewer, path = shared.lemon("reviewer", "done", channel="codex:reviewer", parent=lead)
    shared.link(reviewer, lead)
    exited = {"pid": 999999, "parent": 1, "tty": "ttys099", "started": "", "executable": "codex"}
    state.write("native-" + state.key("codex:reviewer") + ".json", {"identity": exited})

    done_lines = _end(reviewer, lead)

    with db.connect() as conn:
        row = db.get_by_channel(conn, "codex:reviewer", unread_only=False)
        moved = lemon.brief_of(conn, reviewer)
        world = child_place.World(set(), {}, [], {}, [])
        [listed] = children.of(conn, lead, world)
    assert done_lines[0] == "archived its inbox card"
    assert done_lines[-1].startswith("archived its brief to ")
    assert row.is_archived and ended.cause(row.metadata) == ended.ENDED
    assert not path.exists() and moved is not None and archive.is_archived(moved)
    assert (listed.archived, listed.cleanup, listed.held_by) == (True, "cleaned", ())
    assert not children.shown(listed, False) and children.shown(listed, True)
    assert events.entries(1, thing=reviewer)[0]["action"] == "lemon-end"


def test_ending_it_again_changes_nothing():
    author, _ = shared.lemon("author", channel="claude:author")
    reviewer, _ = shared.lemon("reviewer", "done", parent=author)
    _end(reviewer, author)

    assert _end(reviewer, author) == ["its brief was already in the attic"]
