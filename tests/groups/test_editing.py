import pytest

from lemonaid import brief, groups, lineage
from lemonaid.inbox import db
from tests.lineage.shared import lemon


def _line(lemon_id: str) -> tuple[str, ...] | None:
    with db.connect() as conn:
        path = brief.lemon.brief_of(conn, lemon_id)
    assert path
    return groups.line.read(path.read_text())


def test_a_valid_name_cleans_the_wanted_one():
    assert groups.editing.valid_name("fix, the\tbug") == "fix the bug"
    assert groups.editing.valid_name(" ,\n") == "Group"


def test_a_tree_group_with_a_taken_name_adds_the_tree_to_that_group():
    lead, child, other = lemon("lead"), lemon("child"), lemon("other")
    with db.connect() as conn:
        lineage.links.set_parent(conn, child, lead)
        work = groups.store.create(conn, "Work")
        groups.store.add(conn, work, [other])

        edit = groups.editing.group_tree(conn, lead, "Work", "lead")

        assert edit.description == 'Added lead and 1 more to "Work"'
        assert groups.store.find(conn, "Work").members == (other, lead, child)
        with pytest.raises(groups.store.GroupError, match="already in"):
            groups.editing.group_tree(conn, lead, "Work", "lead")
        groups.editing.undo(conn, edit.change)
        assert groups.store.find(conn, "Work").members == (other,)


def test_a_tree_group_holds_the_lemon_and_every_descendant_and_undoes_to_nothing():
    lead, child, grandchild, other = lemon("lead"), lemon("child"), lemon("grand"), lemon("x")
    with db.connect() as conn:
        lineage.links.set_parent(conn, child, lead)
        lineage.links.set_parent(conn, grandchild, child)

        edit = groups.editing.group_tree(conn, lead, "lead", "lead")

    assert edit.group and edit.group.name == "lead"
    assert edit.group.members == (lead, child, grandchild)
    assert edit.description == 'Made group "lead" of lead and 2 more'
    assert _line(grandchild) == ("lead",)
    assert _line(other) is None

    with db.connect() as conn:
        groups.editing.undo(conn, edit.change)
        assert groups.store.all_groups(conn) == []
    assert _line(lead) is None


def test_adding_to_a_new_name_makes_the_group_and_undo_removes_it():
    one = lemon("one")
    with db.connect() as conn:
        edit = groups.editing.add(conn, "Fresh", one, "one")

        assert edit.description == 'Added one to "Fresh" (new)'
        assert groups.store.find(conn, "Fresh").members == (one,)
        groups.editing.undo(conn, edit.change)
        assert groups.store.all_groups(conn) == []
    assert _line(one) is None


def test_removing_and_undoing_puts_the_lemon_back_in_its_place():
    one, two = lemon("one"), lemon("two")
    with db.connect() as conn:
        group = groups.store.create(conn, "Work")
        groups.store.add(conn, group, [one, two])

        edit = groups.editing.remove(conn, group, one, "one")
        assert groups.store.find(conn, "Work").members == (two,)
        assert _line(one) is None
        groups.editing.undo(conn, edit.change)
        assert groups.store.find(conn, "Work").members == (one, two)
    assert _line(one) == ("Work",)


def test_a_deleted_group_comes_back_with_its_place_collapse_and_members():
    one = lemon("one")
    with db.connect() as conn:
        groups.store.create(conn, "First")
        work = groups.store.create(conn, "Work")
        groups.store.add(conn, work, [one])
        groups.arrangement.set_collapsed(conn, work, True)
        work = groups.store.find(conn, "Work")

        edit = groups.editing.delete(conn, work)
        assert _line(one) is None
        groups.editing.undo(conn, edit.change)

        assert groups.store.find(conn, "Work") == work
    assert _line(one) == ("Work",)


def test_rename_rewrites_lines_and_refuses_a_taken_name():
    one, other = lemon("one"), lemon("other")
    with db.connect() as conn:
        work = groups.store.create(conn, "Work")
        groups.store.add(conn, work, [one])
        groups.store.add(conn, groups.store.create(conn, "Taken"), [other])

        with pytest.raises(groups.store.GroupError):
            groups.editing.rename(conn, work, "Taken")
        edit = groups.editing.rename(conn, groups.store.find(conn, "Work"), "Job")
        assert _line(one) == ("Job",)

        groups.editing.undo(conn, edit.change)
    assert _line(one) == ("Work",)


def test_undo_changes_nothing_once_the_group_has_changed_since():
    one, two = lemon("one"), lemon("two")
    with db.connect() as conn:
        work = groups.store.create(conn, "Work")
        edit = groups.editing.add(conn, "Work", one, "one")
        groups.store.add(conn, work, [two])

        with pytest.raises(groups.snapshot.Changed):
            groups.editing.undo(conn, edit.change)

        assert groups.store.find(conn, "Work").members == (one, two)


def test_undo_changes_nothing_when_a_new_group_took_the_deleted_ones_place():
    one = lemon("one")
    with db.connect() as conn:
        work = groups.store.create(conn, "Work")
        groups.store.add(conn, work, [one])
        edit = groups.editing.delete(conn, work)
        groups.store.create(conn, "Work")

        with pytest.raises(groups.store.GroupError):
            groups.editing.undo(conn, edit.change)

        assert [(g.name, g.members) for g in groups.store.all_groups(conn)] == [("Work", ())]


def test_adding_a_member_again_is_refused():
    one = lemon("one")
    with db.connect() as conn:
        groups.store.add(conn, groups.store.create(conn, "Work"), [one])

        with pytest.raises(groups.store.GroupError, match="already in"):
            groups.editing.add(conn, "Work", one, "one")


def test_a_tree_group_with_an_old_empty_groups_name_brings_it_back_and_undo_empties_it():
    one = lemon("one")
    with db.connect() as conn:
        groups.store.create(conn, "First")
        old = groups.store.create(conn, "Old")

        edit = groups.editing.group_tree(conn, one, "Old", "one")
        assert edit.group and (edit.group.group_id, edit.group.members) == (old.group_id, (one,))
        groups.editing.undo(conn, edit.change)

        assert groups.store.find(conn, "Old") == old


def test_renaming_to_an_empty_groups_name_takes_it():
    one = lemon("one")
    with db.connect() as conn:
        groups.store.create(conn, "Old")
        work = groups.store.create(conn, "Work")
        groups.store.add(conn, work, [one])

        renamed = groups.editing.rename(conn, groups.store.find(conn, "Work"), "Old").group

        assert renamed and (renamed.group_id, renamed.members) == (work.group_id, (one,))
        assert [g.name for g in groups.store.all_groups(conn)] == ["Old"]


def test_joining_a_group_its_lemon_is_already_in_counts_only_the_children():
    lead, child, grandchild = lemon("lead"), lemon("child"), lemon("grand")
    with db.connect() as conn:
        lineage.links.set_parent(conn, child, lead)
        lineage.links.set_parent(conn, grandchild, child)
        groups.store.add(conn, groups.store.create(conn, "Work"), [lead])

        edit = groups.editing.group_tree(conn, lead, "Work", "lead")

    assert edit.description == 'Added 2 of lead\'s children to "Work"'
