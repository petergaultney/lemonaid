"""A rerolled Lemon-ID carries its brief, inbox, links, and old name with it."""

import argparse
import json

import pytest

from lemonaid import lineage
from lemonaid.brief import attached, identity, lemon, reroll, store, write_cli
from lemonaid.inbox import db
from lemonaid.messages import cli, waiter
from lemonaid.messages import store as message_store


@pytest.fixture(autouse=True)
def _no_inherited_session_identity(monkeypatch):
    for name in ("LEMONAID_CHANNEL", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX_PANE"):
        monkeypatch.delenv(name, raising=False)


def _lemon(name: str, channel: str) -> str:
    path = store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nLemon-ID: {name}.BloodKeg\n\nStatus: working\n")
    with db.connect() as conn:
        db.add(conn, channel, "", metadata={})
        attached.attach(conn, channel, path)
        return identity.ensure(conn, path)


def _run(*argv: str) -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    cli.add_tell_parser(subparsers)
    write_cli.add_parsers(subparsers)
    inbox = subparsers.add_parser("inbox")
    cli.add_inbox_parsers(inbox.add_subparsers())
    args = parser.parse_args(argv)
    args.func(args)


def _reroll(name: str, chosen: str = "") -> reroll.Rerolled:
    with db.connect() as conn:
        return reroll.reroll(conn, store.briefs_dir() / f"{name}.md", chosen)


def test_reroll_carries_the_inbox_links_and_brief_to_the_new_id():
    parent = _lemon("parent", "claude:parent")
    child = _lemon("child", "claude:child")
    old = _lemon("center", "claude:center")
    with db.connect() as conn:
        lineage.links.set_parent(conn, old, parent)
        lineage.links.set_parent(conn, child, old)
    old_inbox = message_store.inbox_for_id(old)
    message_store.send(old_inbox, "pending", "someone")
    message_store.mark_done(message_store.send(old_inbox, "read", "someone"))

    rerolled = _reroll("center", "quickodd")

    assert rerolled == reroll.Rerolled("center.BloodKeg", "center.QuickOdd")
    new_inbox = message_store.inbox_for_id(rerolled.new_id)
    assert [p.read_text().endswith("pending\n") for p in new_inbox.glob("*.md")] == [True]
    assert len(list((new_inbox / "done").glob("*.md"))) == 1
    assert not list(old_inbox.glob("*.md"))
    assert identity.from_path(store.briefs_dir() / "center.md") == rerolled.new_id
    with db.connect() as conn:
        assert lineage.links.parent_of(conn, rerolled.new_id) == parent
        assert lineage.links.children_of(conn, rerolled.new_id) == [child]
        assert lemon.brief_of(conn, old) == (store.briefs_dir() / "center.md").resolve()
        assert lemon.lemon_id(conn, old) == rerolled.new_id


def test_tell_to_the_old_id_reaches_the_new_inbox(capsys, monkeypatch):
    old = _lemon("center", "claude:center")
    stale_inbox = message_store.inbox_for_id(old)  # a sender that resolved before the reroll
    new = _reroll("center").new_id
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:sender")

    with waiter.armed(message_store.inbox_for_id(new)):
        _run("tell", old, "by old name")
    message_store.send(stale_inbox, "resolved early", "claude:sender")

    new_inbox = message_store.inbox_for_id(new)
    assert sorted(p.read_text().rsplit("\n", 2)[-2] for p in new_inbox.glob("*.md")) == [
        "by old name",
        "resolved early",
    ]
    assert not list(stale_inbox.glob("*.md"))


def test_a_second_reroll_keeps_every_earlier_id_one_hop_away():
    first = _lemon("center", "claude:center")
    second = _reroll("center").new_id
    third = _reroll("center").new_id

    with db.connect() as conn:
        assert lemon.current(conn, first) == third
        assert lemon.current(conn, second) == third
    message_store.send(message_store.inbox_for_id(first), "oldest", "someone")
    assert len(list(message_store.inbox_for_id(third).glob("*.md"))) == 1


@pytest.mark.parametrize(
    ("chosen", "error"),
    [
        ("Nope", "not a valid WordyBin word"),
        ("Quick", "not a two-word WordyBin"),
        ("BloodKeg", "already has that WordyBin"),
        ("SkullHen", "is, or was, another lemon's"),
    ],
)
def test_set_refuses_a_bad_or_taken_wordybin(chosen, error):
    _lemon("center", "claude:center")
    other = store.briefs_dir() / "other.md"
    other.write_text("# other\n\nLemon-ID: center.SkullHen\n")
    with db.connect() as conn:
        identity.ensure(conn, other)

    with pytest.raises(ValueError, match=error):
        _reroll("center", chosen)

    assert identity.from_path(store.briefs_dir() / "center.md") == "center.BloodKeg"


def test_a_failed_brief_rewrite_leaves_everything_as_it_was(monkeypatch):
    old = _lemon("center", "claude:center")
    message_store.send(message_store.inbox_for_id(old), "pending", "someone")

    def refuse(path, change):
        raise store.ChangedUnderneath("busy")

    monkeypatch.setattr(store, "edit", refuse)
    with pytest.raises(store.ChangedUnderneath):
        _reroll("center", "QuickOdd")

    inbox = message_store.inbox_for_id(old)
    assert len(list(inbox.glob("*.md"))) == 1
    assert not (inbox / message_store.FORWARD).exists()
    assert not message_store.inbox_for_id("center.QuickOdd").exists()
    with db.connect() as conn:
        assert lemon.brief_of(conn, old) is not None
        assert lemon.current(conn, old) == old


def test_the_old_waiter_exits_asking_to_rearm(capsys, monkeypatch):
    _lemon("center", "claude:center")

    def rerolled_watch(inbox_path, still_attached, timeout, find):
        _reroll("center", "QuickOdd")
        still_attached()

    monkeypatch.setattr(message_store, "watch_next", rerolled_watch)
    with pytest.raises(SystemExit, match="1"):
        _run("inbox", "watch", "--self", "--channel", "claude:center")

    assert "Lemon-ID changed to center.QuickOdd; rearm" in capsys.readouterr().err


def test_cli_prints_old_and_new_signing_names(capsys):
    _lemon("center", "claude:center")

    _run("id", "--channel", "claude:center", "--set", "QuickOdd", "--json")

    result = json.loads(capsys.readouterr().out)
    assert result["lemon_id"] == "center.QuickOdd"
    assert result["old_lemon_id"] == "center.BloodKeg"
    assert (result["signing_name"], result["old_signing_name"]) == ("QuickOdd", "BloodKeg")


def test_a_failed_forward_write_puts_the_inbox_back(monkeypatch):
    old = _lemon("center", "claude:center")
    message_store.send(message_store.inbox_for_id(old), "pending", "someone")
    monkeypatch.setattr(message_store, "FORWARD", "missing/.forward")

    with pytest.raises(FileNotFoundError):
        _reroll("center", "QuickOdd")

    assert len(list(message_store.inbox_for_id(old).glob("*.md"))) == 1
    assert not message_store.inbox_for_id("center.QuickOdd").exists()
    assert identity.from_path(store.briefs_dir() / "center.md") == old


def test_a_new_brief_cannot_take_an_old_id(monkeypatch):
    _lemon("center", "claude:center")
    _reroll("center", "QuickOdd")
    squatter = store.briefs_dir() / "squatter.md"
    squatter.write_text("# squatter\n\nLemon-ID: center.BloodKeg\n")

    with db.connect() as conn, pytest.raises(ValueError, match="old ID of center.QuickOdd"):
        identity.ensure(conn, squatter)

    words = iter((b"\xbd\xbb", b"\0\0"))  # SkullHen, then a free one
    monkeypatch.setattr(store.os, "urandom", lambda size: next(words))
    other = store.briefs_dir() / "center-again.md"
    other.write_text("# center\n")
    with db.connect() as conn:
        conn.execute("INSERT INTO lemon_aliases VALUES ('center-again.SkullHen', 'x.Y')")
        conn.commit()
        assert identity.ensure(conn, other) != "center-again.SkullHen"
