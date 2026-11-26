from lemonaid import groups
from lemonaid.grove.layout import state
from lemonaid.grove.source import block_numbers
from lemonaid.inbox import db
from tests.grove.shared import block


def test_a_home_group_is_saved_and_cleared_and_a_group_must_exist():
    with db.connect() as conn:
        groups.store.create(conn, "meyer")
    assert block_numbers.set_home("meyer") == '"meyer" is in the home block'
    assert state.load()["home"] == "meyer"
    assert block_numbers.set_home("nobody") == "No group named 'nobody'"
    assert block_numbers.set_home("") == "the home block holds only lemons in no group"
    assert "home" not in state.load()


def test_renumbering_trades_a_block_with_its_neighbour_and_stops_at_the_ends():
    with db.connect() as conn:
        for name in ("a", "b", "c"):
            groups.store.create(conn, name)
    found = (block("a", "1"), block("b", "2"), block("c", "3"), block("", "0"))
    assert block_numbers.renumber(found, "2", -1) == '"b" is block 1'
    with db.connect() as conn:
        assert [g.name for g in groups.store.all_groups(conn)] == ["b", "a", "c"]
    assert block_numbers.renumber(found, "3", 1) == "block 3 is already last"
    assert block_numbers.renumber(found, "0", -1) == "only a group's block has a number to change"
