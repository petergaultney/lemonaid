from lemonaid import groups
from lemonaid.brief import attached, check, identity, store
from lemonaid.brief.lemon import lemon_id
from lemonaid.inbox import db
from tests.lineage.shared import lemon

from .shared import run


def _text(name: str) -> str:
    return (store.briefs_dir() / f"{name}.md").read_text()


def test_group_changes_rewrite_each_members_line(capsys):
    one = lemon("one")
    run(capsys, "group", "create", "A", one, "--json")
    run(capsys, "group", "create", "B", one, "--json")
    assert groups.line.read(_text("one")) == ("A", "B")

    run(capsys, "group", "rename", "A", "Alpha", "--json")
    assert groups.line.read(_text("one")) == ("Alpha", "B")

    run(capsys, "group", "remove", "B", one, "--json")
    assert groups.line.read(_text("one")) == ("Alpha",)

    run(capsys, "group", "delete", "Alpha", "--json")
    assert groups.line.read(_text("one")) is None


def test_a_brief_new_to_this_database_brings_its_groups_in():
    path = store.briefs_dir() / "moved.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# moved\n\nBrief-ID: moved.Xy\n\nStatus: working\nGroups: Relay, Inbox\n")

    with db.connect() as conn:
        registered = identity.ensure(conn, path)

        assert groups.store.names_of(conn, registered) == ("Relay", "Inbox")


def test_a_known_brief_keeps_the_databases_groups(capsys):
    one = lemon("one")
    path = store.briefs_dir() / "one.md"
    path.write_text(path.read_text().replace("Status: working", "Status: working\nGroups: Stray"))

    with db.connect() as conn:
        identity.ensure(conn, path)

        assert groups.store.names_of(conn, one) == ()
        assert check.groups_line(conn, path.read_text()) == [
            "The `Groups:` line names groups this brief isn't in; remove it"
        ]


def test_check_reports_a_line_a_hand_edit_dropped(capsys):
    one = lemon("one")
    run(capsys, "group", "create", "A", one, "--json")
    path = store.briefs_dir() / "one.md"
    path.write_text(groups.line.written(path.read_text(), []))

    with db.connect() as conn:
        assert check.groups_line(conn, path.read_text()) == [
            "The `Groups:` line should read `Groups: A`"
        ]


def test_sync_sets_groups_from_the_line(capsys):
    one = lemon("one")
    path = store.briefs_dir() / "one.md"
    path.write_text(groups.line.written(path.read_text(), ["From", "File"]))

    synced = run(capsys, "group", "sync", one, "--json")

    assert synced["lemons"] == [{"lemon_id": one, "groups": ["From", "File"]}]


def test_sync_leaves_groups_alone_when_the_brief_has_no_line(capsys):
    one = lemon("one")
    run(capsys, "group", "create", "Kept", one, "--json")
    path = store.briefs_dir() / "one.md"
    path.write_text(groups.line.written(path.read_text(), []))

    synced = run(capsys, "group", "sync", one, "--json")

    assert synced["lemons"] == [{"lemon_id": one, "groups": None}]
    with db.connect() as conn:
        assert groups.store.names_of(conn, one) == ("Kept",)


def test_check_is_quiet_about_a_line_not_yet_read_in():
    path = store.briefs_dir() / "arrived.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# arrived\n\nBrief-ID: arrived.Xy\n\nStatus: working\nGroups: Relay\n")

    with db.connect() as conn:
        assert check.groups_line(conn, path.read_text()) == []


def test_a_replacement_session_on_the_same_brief_keeps_its_groups(capsys):
    one = lemon("one", "claude:old")
    run(capsys, "group", "create", "A", one, "--json")

    with db.connect() as conn:
        db.archive_channel(conn, "claude:old", "test")
        db.add(conn, "claude:new", "", metadata={})
        attached.attach(conn, "claude:new", store.briefs_dir() / "one.md")
        assert groups.store.names_of(conn, lemon_id(conn, "claude:new")) == ("A",)
