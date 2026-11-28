from lemonaid.groups import store
from lemonaid.grove.web import group_edit, server
from lemonaid.inbox import db


def _group(name: str, *lemons: str) -> None:
    with db.connect() as conn:
        store.add(conn, store.create(conn, name), lemons)


def _names() -> list[str]:
    with db.connect() as conn:
        return [g.name for g in store.all_groups(conn) if g.members]


def test_a_phone_may_edit_a_group_by_its_name():
    assert {"group_edit", "group_edit_info"} <= server._CALLS


def test_a_group_is_renamed_recolored_and_deleted_with_its_lemons_left_alone():
    _group("alpha", "one", "two")

    assert group_edit.info("alpha") == {"problem": "", "name": "alpha", "color": "", "members": 2}
    assert group_edit.make("rename", "alpha", "beta") == 'Renamed group "alpha" to "beta"'
    assert group_edit.make("color", "beta", "teal").startswith('Set group "beta" to #')
    assert group_edit.info("beta")["color"].startswith("#")
    assert group_edit.make("color", "beta", "") == 'Cleared the saved color of group "beta"'
    assert group_edit.make("delete", "beta", "") == 'Deleted group "beta"'
    assert _names() == []


def test_an_edit_that_cant_be_made_says_why():
    _group("alpha", "one")
    _group("beta", "two")

    assert "already exists" in group_edit.make("rename", "alpha", "beta")
    assert "isn't a color" in group_edit.make("color", "alpha", "not-a-color")
    assert "No group named" in group_edit.make("delete", "gone", "")
    assert group_edit.make("move", "alpha", "") == "no edit move"
    assert group_edit.info("gone")["problem"].startswith("No group named")
    assert _names() == ["alpha", "beta"]
