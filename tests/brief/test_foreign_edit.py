from lemonaid.audit import events
from lemonaid.brief import identity, store, verbs_cli
from lemonaid.inbox import db


def _brief() -> tuple:
    path = store.briefs_dir() / "work.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# work\n\n## Now\n\n- Started.\n")
    with db.connect() as conn:
        return path.resolve(), identity.ensure(conn, path)


def test_an_edit_by_anyone_but_the_briefs_own_lemon_is_audited(monkeypatch):
    path, lemon_id = _brief()
    monkeypatch.setattr(verbs_cli.created, "by", lambda conn: "OtherOne")

    assert verbs_cli.edit(path, lambda text: store.with_status(text, "blocked")) == ""

    [entry] = events.entries(0)
    assert (entry["action"], entry["thing"], entry["brief"]) == ("brief-edit", lemon_id, str(path))


def test_a_lemon_editing_its_own_brief_is_not_audited(monkeypatch):
    path, lemon_id = _brief()
    monkeypatch.setattr(verbs_cli.created, "by", lambda conn: identity.brief_name(lemon_id))

    assert verbs_cli.edit(path, lambda text: store.with_status(text, "blocked")) == ""

    assert events.entries(0) == []
