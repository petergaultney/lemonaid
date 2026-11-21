import pytest

from lemonaid.grove import grafts
from lemonaid.inbox import db


def test_a_new_graft_replaces_the_old_and_ungrafting_by_any_name_removes_it():
    with db.connect() as conn:
        grafts.graft(conn, "StoveHub.review", "SillyOil.window")
        grafts.graft(conn, "StoveHub.review", "BlessBar.plan")
        assert grafts.recorded(conn) == {"StoveHub.review": "BlessBar.plan"}
        assert grafts.ungraft(conn, ["claude:stove", "StoveHub.review"]) == 1
        assert grafts.ungraft(conn, ["StoveHub.review"]) == 0
        assert grafts.recorded(conn) == {}


def test_a_graft_onto_itself_or_into_a_loop_is_refused():
    with db.connect() as conn:
        grafts.graft(conn, "b", "c")
        grafts.graft(conn, "c", "d")
        with pytest.raises(grafts.GraftError, match="its own tree"):
            grafts.graft(conn, "a", "a")
        with pytest.raises(grafts.GraftError, match="b is grafted onto d's tree"):
            grafts.graft(conn, "d", "b")
        assert grafts.recorded(conn) == {"b": "c", "c": "d"}
