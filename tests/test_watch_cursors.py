"""Whose cursors a waiter uses: its lemon's, by Lemon-ID, whatever signature it was given."""

from lemonaid.brief import attached, identity, store
from lemonaid.inbox import db
from lemonaid.watch import cursors


def _lemon(channel: str) -> str:
    path = store.briefs_dir() / "author.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# author\n\nLemon-ID: author.BloodKeg\n")
    with db.connect() as conn:
        db.add(conn, channel, "", metadata={})
        attached.attach(conn, channel, path)
        return identity.ensure(conn, path)


def test_a_lemon_with_a_brief_keeps_one_set_of_cursors_for_every_signature(monkeypatch):
    lemon_id = _lemon("codex:thread-1")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")

    assert cursors.directory("pr", "Author (BloodKeg)") == cursors.root() / lemon_id / "pr"
    assert cursors.directory("pr", "Reviewer (BloodKeg)") == cursors.root() / lemon_id / "pr"


def test_a_codex_thread_names_its_lemon():
    lemon_id = _lemon("codex:thread-1")

    assert cursors.owner("Author (BloodKeg)", "thread-1") == lemon_id


def test_without_a_brief_the_signature_is_the_key():
    assert cursors.owner("Author (X)") != cursors.owner("Reviewer (X)")
    assert cursors.owner("") == "anonymous"


def test_without_a_brief_or_signature_each_session_keeps_its_own(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    first = cursors.owner("")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s2")

    assert first != cursors.owner("") != "anonymous"


def test_cursors_live_in_the_state_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path / "elsewhere"))

    assert cursors.root() == tmp_path / "elsewhere" / "cursors"
