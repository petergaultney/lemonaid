import pytest

from tests.lineage.shared import lemon

from .shared import members, run


def test_a_group_holds_the_lemons_it_was_created_with(capsys):
    one, two = lemon("one", "claude:one"), lemon("two")

    created = run(capsys, "group", "create", "Inbox work", one, "two", "--json")

    assert created["group"]["name"] == "Inbox work"
    assert members(created) == [one, two]
    assert created["group"]["members"][0]["channel"] == "claude:one"
    assert created["group"]["members"][1]["status"] == ""


def test_a_lemon_can_be_in_more_than_one_group(capsys, monkeypatch):
    me = lemon("me", "claude:me")
    run(capsys, "group", "create", "First", "--json")
    run(capsys, "group", "create", "Second", "--json")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:me")

    run(capsys, "group", "add", "First", "self", "--json")
    run(capsys, "group", "add", "Second", "self", "--json")
    mine = run(capsys, "group", "list", "--self", "--json")

    assert [g["name"] for g in mine["groups"]] == ["First", "Second"]
    assert all(g["members"][0]["lemon_id"] == me for g in mine["groups"])


def test_tree_takes_every_descendant_of_a_lead(capsys):
    lead, child, grandchild, other = (
        lemon("lead"),
        lemon("child"),
        lemon("grandchild"),
        lemon("other"),
    )
    run(capsys, "lemon", "parent", child, "--set", lead, "--json")
    run(capsys, "lemon", "parent", grandchild, "--set", child, "--json")

    created = run(capsys, "group", "create", "Lead's work", lead, "--tree", "--json")

    assert members(created) == [lead, child, grandchild]
    assert other not in members(created)


def test_adding_a_member_twice_reports_only_the_first(capsys):
    one = lemon("one")
    run(capsys, "group", "create", "G", "--json")

    first = run(capsys, "group", "add", "G", one, "--json")
    again = run(capsys, "group", "add", "G", one, "--json")

    assert first["added"] == [one]
    assert again["added"] == []
    assert members(again) == [one]


def test_remove_takes_a_lemon_out_of_one_group_only(capsys):
    one = lemon("one")
    run(capsys, "group", "create", "A", one, "--json")
    run(capsys, "group", "create", "B", one, "--json")

    removed = run(capsys, "group", "remove", "A", one, "--json")

    assert removed["removed"] == [one]
    assert members(removed) == []
    assert [
        g["name"] for g in run(capsys, "group", "list", "--lemon", one, "--json")["groups"]
    ] == ["B"]


def test_rename_keeps_members_and_refuses_a_taken_name(capsys):
    one = lemon("one")
    run(capsys, "group", "create", "Old", one, "--json")
    run(capsys, "group", "create", "Taken", one, "--json")

    refused = run(capsys, "group", "rename", "Old", "Taken", "--json")
    renamed = run(capsys, "group", "rename", "Old", "New", "--json")

    assert "already exists" in refused["error"]
    assert renamed["group"]["name"] == "New"
    assert members(renamed) == [one]


def test_delete_forgets_the_group_and_its_memberships(capsys):
    one = lemon("one")
    run(capsys, "group", "create", "Gone", one, "--json")

    run(capsys, "group", "delete", "Gone", "--json")
    run(capsys, "group", "create", "Gone", "--json")

    assert run(capsys, "group", "list", "--lemon", one, "--json")["groups"] == []


def test_groups_list_in_the_order_they_were_made(capsys):
    lemon("one")
    for name in ("b", "a", "c"):
        run(capsys, "group", "create", name, "one", "--json")

    assert [g["name"] for g in run(capsys, "group", "list", "--json")["groups"]] == ["b", "a", "c"]


def test_group_move_sets_a_one_based_position_and_keeps_order_persisted(capsys):
    one = lemon("one")
    for name in ("First", "Second", "Third"):
        run(capsys, "group", "create", name, one, "--json")

    moved = run(capsys, "group", "move", "Third", "--to", "1", "--json")

    assert moved["group"]["position"] == 10.0
    assert [g["name"] for g in run(capsys, "group", "list", "--json")["groups"]] == [
        "Third",
        "First",
        "Second",
    ]


def test_group_move_up_and_down_and_invalid_positions(capsys):
    one = lemon("one")
    for name in ("First", "Second", "Third"):
        run(capsys, "group", "create", name, one, "--json")

    run(capsys, "group", "move", "Third", "--up", "--json")
    run(capsys, "group", "move", "First", "--down", "--json")
    assert run(capsys, "group", "move", "Third", "--up", "--json")["error"] is None
    assert run(capsys, "group", "move", "Second", "--down", "--json")["error"] is None
    assert [g["name"] for g in run(capsys, "group", "list", "--json")["groups"]] == [
        "Third",
        "First",
        "Second",
    ]
    assert (
        "Position must be between"
        in run(capsys, "group", "move", "First", "--to", "4", "--json")["error"]
    )


def test_a_group_with_no_members_is_not_listed_and_making_it_again_brings_it_back(capsys):
    lemon("one")
    run(capsys, "group", "create", "First", "--json")
    first = run(capsys, "group", "create", "Old", "one", "--json")["group"]
    run(capsys, "group", "remove", "Old", "one", "--json")

    listed = [g["name"] for g in run(capsys, "group", "list", "--json")["groups"]]
    again = run(capsys, "group", "create", "Old", "--json")

    assert listed == []
    assert again["error"] is None and again["group"]["position"] == first["position"]
    run(capsys, "group", "add", "Old", "one", "--json")
    assert run(capsys, "group", "create", "Old", "--json")["error"]  # it has a member again


def test_a_missing_group_or_lemon_is_an_error(capsys):
    lemon("one")

    assert "No group named" in run(capsys, "group", "add", "Nope", "one", "--json")["error"]
    run(capsys, "group", "create", "G", "--json")
    assert run(capsys, "group", "add", "G", "nobody", "--json")["error"]


def test_a_blank_name_is_refused(capsys):
    assert "needs a name" in run(capsys, "group", "create", "  ", "--json")["error"]


def test_text_output_lists_each_member_under_its_group(capsys):
    one = lemon("one", "claude:one")
    run(capsys, "group", "create", "G", one, "--json")

    assert run(capsys, "group", "list")["out"] == f"G\n\t{one}\t-\tclaude:one\n"


def test_a_name_with_a_comma_is_refused(capsys):
    assert "comma" in run(capsys, "group", "create", "a, b", "--json")["error"]


def test_a_group_color_is_saved_and_cleared(capsys):
    run(capsys, "group", "create", "Work", "--json")

    saved = run(capsys, "group", "color", "Work", "tomato", "--json")
    cleared = run(capsys, "group", "color", "Work", "--clear", "--json")
    refused = run(capsys, "group", "color", "Work", "nope", "--json")

    assert saved["group"]["color"] == "#ff6347"
    assert cleared["group"]["color"] == ""
    assert "isn't a color" in refused["error"]


def test_a_group_color_needs_a_color_or_clear(capsys):
    run(capsys, "group", "create", "Work", "--json")

    with pytest.raises(SystemExit):
        run(capsys, "group", "color", "Work")
