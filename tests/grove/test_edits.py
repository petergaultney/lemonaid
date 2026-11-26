import itertools

from lemonaid import groups
from lemonaid.grove import grafts
from lemonaid.grove.source import changes
from lemonaid.grove.tui.picking import Target
from lemonaid.inbox import db, pins

_ids = itertools.count(5100)


def _lemon(name: str) -> str:
    with db.connect() as conn:
        db.add(conn, f"claude:{name}", "a message", name, {"tty": f"/dev/ttys{next(_ids)}"})
    return f"claude:{name}"


def _target(action: str, *channels: str, channel: str = "", block: str = "") -> Target:
    return Target(
        action, block, (block,), "tree", channel, "tree", tuple((c, "") for c in channels)
    )


def test_pinning_a_tree_pins_every_lemon_and_again_unpins_them():
    a, b = _lemon("pin-a"), _lemon("pin-b")
    assert changes.pin(_target("pin", a, b)) == "pinned 2 lemons"
    with db.connect() as conn:
        assert pins.is_pinned(conn, a) and pins.is_pinned(conn, b)
    assert changes.pin(_target("pin", a, b)) == "unpinned 2 lemons"


def test_archiving_one_lemon_leaves_its_sibling():
    a, b = _lemon("arch-a"), _lemon("arch-b")
    assert changes.archive(_target("archive", a, b, channel=a)) == "archived 1 lemon"
    with db.connect() as conn:
        assert db.get_by_channel(conn, a, unread_only=True) is None
        assert db.get_by_channel(conn, b, unread_only=True) is not None


def test_moving_a_lemon_takes_it_out_of_its_group_and_into_the_other():
    a = _lemon("move-a")
    with db.connect() as conn:
        groups.store.add(conn, groups.store.create(conn, "from"), [a])
        groups.store.create(conn, "to")
    assert changes.move(_target("group", a, block="from"), "to") == 'moved 1 lemon to "to"'
    with db.connect() as conn:
        assert a not in groups.store.find(conn, "from").members
        assert a in groups.store.find(conn, "to").members


def test_moving_to_a_group_it_is_in_already_still_takes_it_out_of_its_own():
    a, b = _lemon("overlap-a"), _lemon("overlap-b")
    with db.connect() as conn:
        groups.store.add(conn, groups.store.create(conn, "here"), [a, b])
        groups.store.add(conn, groups.store.create(conn, "there"), [a])
    assert (
        changes.move(_target("group", a, b, block="here"), "there") == 'moved 2 lemons to "there"'
    )
    with db.connect() as conn:
        assert groups.store.find(conn, "here").members == ()
        assert set(groups.store.find(conn, "there").members) == {a, b}


def test_grafting_a_tree_moves_each_lemon_and_back_ungrafts_them():
    a, b, host = _lemon("graft-a"), _lemon("graft-b"), _lemon("graft-host")
    assert changes.graft(_target("graft", a, b), host) == f"grafted 2 lemons onto {host}"
    with db.connect() as conn:
        assert {a: host, b: host}.items() <= grafts.recorded(conn).items()
    assert (
        changes.graft(_target("graft", host), a)
        == f"{a} is grafted onto {host}'s tree; ungraft it first"
    )
    assert changes.graft(_target("graft", a, b), "") == "ungrafted 2 lemons"
    assert changes.graft(_target("graft", a, b), "") == "no graft to undo"


def test_moving_out_of_block_0_leaves_the_home_group_and_an_ungrouped_lemon_just_joins():
    homed, loose = _lemon("home-a"), _lemon("home-b")
    with db.connect() as conn:
        groups.store.add(conn, groups.store.create(conn, "meyer"), [homed])
        groups.store.create(conn, "away")
    assert changes.move(_target("group", homed, loose, block="meyer"), "away") == (
        'moved 2 lemons to "away"'
    )
    with db.connect() as conn:
        assert groups.store.find(conn, "meyer").members == ()
        assert set(groups.store.find(conn, "away").members) == {homed, loose}
