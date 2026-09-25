"""File messages travel by attached lemon channel without consulting tmux."""

import argparse
import io
import sys
import threading
import time
from pathlib import Path

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db, self_session
from lemonaid.messages import cli, store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    cli.add_tell_parser(subparsers)
    inbox = subparsers.add_parser("inbox")
    cli.add_inbox_parsers(inbox.add_subparsers())
    return parser


@pytest.fixture(autouse=True)
def _no_inherited_session_identity(monkeypatch):
    for name in ("LEMONAID_CHANNEL", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX_PANE"):
        monkeypatch.delenv(name, raising=False)


def _run(parser: argparse.ArgumentParser, *arguments: str) -> None:
    args = parser.parse_args(arguments)
    args.func(args)


def _attach(channel: str, name: str) -> None:
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n")
    with db.connect() as conn:
        db.add(conn, channel, "", metadata={})
        attached.attach(conn, channel, path)


def _inbox(name: str) -> Path:
    with db.connect() as conn:
        lemon_id = identity.ensure(conn, brief_store.briefs_dir() / f"{name}.md")

    return store.inbox_for_id(lemon_id)


def test_send_and_receive_by_channel_without_tmux(capsys, monkeypatch):
    _attach("codex:recipient", "recipient")
    parser = _parser()
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:sender")

    _run(parser, "tell", "codex:recipient", "Please review.\nSecond line.")
    sent = capsys.readouterr().out.strip()
    inbox = _inbox("recipient")
    assert sent.startswith(str(inbox))
    assert identity.valid(inbox.name)
    assert len(list(inbox.glob("*.md"))) == 1

    _run(parser, "inbox", "next", "--self", "--channel", "codex:recipient")
    output = capsys.readouterr().out
    assert output.startswith("From: claude:sender\nSent: ")
    assert output.endswith("\n\nPlease review.\nSecond line.\n")
    assert not list(inbox.glob("*.md"))
    assert len(list((inbox / "done").glob("*.md"))) == 1

    with pytest.raises(SystemExit, match="1"):
        _run(parser, "inbox", "next", "--self", "--channel", "codex:recipient")


def test_brief_name_selects_target_and_self_uses_environment(capsys, monkeypatch):
    _attach("codex:recipient", "recipient")
    monkeypatch.setenv("LEMONAID_CHANNEL", "codex:recipient")
    parser = _parser()

    _run(parser, "tell", "recipient", "Hello")
    capsys.readouterr()
    _run(parser, "inbox", "next", "--self")

    assert "Hello" in capsys.readouterr().out


def test_id_target_and_renamed_brief_keep_the_same_inbox(capsys, monkeypatch):
    _attach("codex:recipient", "recipient")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:sender")
    parser = _parser()
    inbox = _inbox("recipient")

    _run(parser, "tell", "recipient", "Before rename")
    capsys.readouterr()
    old = brief_store.briefs_dir() / "recipient.md"
    renamed = old.rename(old.with_name("new-name.md"))
    with db.connect() as conn:
        conn.execute(
            "UPDATE session_briefs SET path = ? WHERE channel = ?",
            (str(renamed), "codex:recipient"),
        )
        conn.commit()

    _run(parser, "tell", inbox.name, "After rename")
    capsys.readouterr()
    assert len(list(inbox.glob("*.md"))) == 2
    assert not (store.inbox_root() / "new-name").exists()

    _run(parser, "inbox", "next", "--self", "--channel", "codex:recipient")
    assert "Before rename" in capsys.readouterr().out
    _run(parser, "inbox", "next", "--self", "--channel", "codex:recipient")
    assert "After rename" in capsys.readouterr().out


@pytest.mark.parametrize("old_id", ["b0045249ad7b4b9c8dc5bd744f485a18", "hand-made.id 123"])
def test_existing_id_keeps_its_inbox_and_receives_messages(capsys, old_id):
    _attach("codex:recipient", "recipient")
    brief_path = brief_store.briefs_dir() / "recipient.md"
    brief_path.write_text(f"# recipient\n\nLemon-ID: {old_id}\n")
    parser = _parser()

    _run(parser, "tell", "codex:recipient", "By channel")
    capsys.readouterr()
    _run(parser, "tell", old_id, "By ID")
    capsys.readouterr()

    inbox = store.inbox_for_id(old_id)
    assert len(list(inbox.glob("*.md"))) == 2
    _run(parser, "inbox", "next", "--self", "--channel", "codex:recipient")
    assert "By channel" in capsys.readouterr().out
    _run(parser, "inbox", "next", "--self", "--channel", "codex:recipient")
    assert "By ID" in capsys.readouterr().out
    assert len(list((inbox / "done").glob("*.md"))) == 2


def test_id_path_rejects_traversal_and_symlink(capsys, monkeypatch, tmp_path):
    _attach("codex:recipient", "recipient")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:sender")
    with pytest.raises(ValueError, match="Invalid lemon ID"):
        store.inbox_for_id("../escape")
    for invalid in ("", ".hidden", "a" * 256, "SwordOwnPanelHadShaftNagFilmyLap/../"):
        with pytest.raises(ValueError, match="Invalid lemon ID"):
            store.inbox_for_id(invalid)

    inbox = _inbox("recipient")
    outside = tmp_path / "outside"
    outside.mkdir()
    inbox.parent.mkdir(parents=True)
    inbox.symlink_to(outside)
    with pytest.raises(SystemExit, match="1"):
        _run(_parser(), "tell", "recipient", "Must stay inside")

    assert "symlink" in capsys.readouterr().err
    assert list(outside.iterdir()) == []


def test_watch_follows_the_id_when_the_brief_filename_changes(capsys, monkeypatch):
    _attach("codex:recipient", "recipient")
    inbox = _inbox("recipient")
    store.send(inbox, "After rename", "claude:sender")

    def renamed_watch(inbox_path, still_attached, timeout, find):
        old = brief_store.briefs_dir() / "recipient.md"
        renamed = old.rename(old.with_name("new-name.md"))
        with db.connect() as conn:
            conn.execute(
                "UPDATE session_briefs SET path = ? WHERE channel = ?",
                (str(renamed), "codex:recipient"),
            )
            conn.commit()
        assert still_attached()
        return find(inbox_path)

    monkeypatch.setattr(store, "watch_next", renamed_watch)
    _run(_parser(), "inbox", "watch", "--self", "--channel", "codex:recipient")

    assert "After rename" in capsys.readouterr().out


def test_watch_stops_when_the_brief_moves_to_another_channel(capsys, monkeypatch):
    _attach("codex:old", "recipient")
    inbox = _inbox("recipient")
    store.send(inbox, "After reattach", "claude:sender")

    def moved_watch(inbox_path, still_attached, timeout, find):
        with db.connect() as conn:
            attached.attach(conn, "codex:new", brief_store.briefs_dir() / "recipient.md")
        assert not still_attached()
        raise ValueError("Brief is no longer attached to this lemon")

    monkeypatch.setattr(store, "watch_next", moved_watch)
    with pytest.raises(SystemExit, match="1"):
        _run(_parser(), "inbox", "watch", "--self", "--channel", "codex:old")

    assert "no longer attached" in capsys.readouterr().err
    assert len(list(inbox.glob("*.md"))) == 1


def test_direct_id_target_skips_another_invalid_brief(capsys, monkeypatch):
    _attach("codex:recipient", "recipient")
    _attach("codex:invalid", "invalid")
    inbox = _inbox("recipient")
    _inbox("invalid")
    bad = brief_store.briefs_dir() / "invalid.md"
    bad.write_text(bad.read_text().replace("Lemon-ID: ", "Lemon-ID: ."))
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:sender")
    warnings = []
    monkeypatch.setattr(cli._log, "warning", lambda *args: warnings.append(args))

    _run(_parser(), "tell", inbox.name, "Hello")

    assert len(list(inbox.glob("*.md"))) == 1
    assert warnings[0][0].startswith("Skipping invalid brief")
    capsys.readouterr()


def test_watch_delivers_one_message_then_exits(tmp_path):
    inbox = tmp_path / "messages"
    results = []
    thread = threading.Thread(
        target=lambda: results.append(store.watch_next(inbox, lambda: True, interval=0.01))
    )
    thread.start()
    try:
        time.sleep(0.02)
        store.send(inbox, "Wake up", "claude:sender")
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert results[0][1].endswith("Wake up\n")
        assert results[0][0].parent == inbox / "done"
    finally:
        thread.join(timeout=2)


def test_parent_and_child_selectors_report_missing_links(capsys):
    parser = _parser()
    for selection in (("--parent", "Hello"), ("--child", "reviewer", "Hello")):
        with pytest.raises(SystemExit, match="1"):
            _run(parser, "tell", *selection)

        assert "require lemon parent links" in capsys.readouterr().err


def test_receiving_requires_known_channel_and_attached_brief(capsys, monkeypatch):
    parser = _parser()
    monkeypatch.delenv("LEMONAID_CHANNEL", raising=False)
    with pytest.raises(SystemExit, match="1"):
        _run(parser, "inbox", "next", "--self")
    assert "Cannot identify this lemon" in capsys.readouterr().err

    with pytest.raises(SystemExit, match="1"):
        _run(parser, "inbox", "next", "--self", "--channel", "codex:unknown")
    assert "No brief attached" in capsys.readouterr().err


def test_claude_session_id_resolves_self_and_labels_sender(capsys, monkeypatch):
    _attach("claude:12345678", "sender")
    _attach("codex:recipient", "recipient")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "12345678-long-session-id")
    parser = _parser()

    _run(parser, "tell", "recipient", "Hello")
    assert f"From: {_inbox('sender').name}" in next(_inbox("recipient").glob("*.md")).read_text()
    capsys.readouterr()
    store.send(_inbox("sender"), "Reply", "codex:recipient")
    _run(parser, "inbox", "next", "--self")

    assert "Reply" in capsys.readouterr().out


def test_codex_thread_id_resolves_self(capsys, monkeypatch):
    _attach("codex:abcdefgh", "mine")
    monkeypatch.setenv("CODEX_THREAD_ID", "abcdefgh-long-thread-id")
    store.send(_inbox("mine"), "Hello", "claude:sender")

    _run(_parser(), "inbox", "next", "--self")

    assert "Hello" in capsys.readouterr().out


def test_explicit_sender_channel_overrides_environment(capsys, monkeypatch):
    _attach("codex:recipient", "recipient")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:wrong")

    _run(_parser(), "tell", "--channel", "codex:right", "recipient", "Hello")

    assert "From: codex:right" in next(_inbox("recipient").glob("*.md")).read_text()
    capsys.readouterr()


def test_tell_from_a_plain_shell_uses_the_user_label(capsys, monkeypatch):
    _attach("codex:recipient", "recipient")
    monkeypatch.setenv("USER", "peter")

    _run(_parser(), "tell", "recipient", "Hello")

    assert "From: peter" in next(_inbox("recipient").glob("*.md")).read_text()
    capsys.readouterr()


def test_tell_from_a_tmux_pane_without_a_lemon_uses_the_user_label(capsys, monkeypatch):
    _attach("codex:recipient", "recipient")
    monkeypatch.setenv("USER", "peter")
    monkeypatch.setenv("TMUX_PANE", "%9")
    monkeypatch.setattr(self_session, "pane_location", lambda pane: None)

    _run(_parser(), "tell", "recipient", "Hello")

    assert "From: peter" in next(_inbox("recipient").glob("*.md")).read_text()
    capsys.readouterr()


def test_tmux_fallback_resolves_self_without_harness_id(capsys, monkeypatch):
    _attach("codex:mine", "mine")
    where = self_session.PaneLocation("/dev/ttys7", "work", "4")
    with db.connect() as conn:
        db.add(
            conn,
            "codex:mine",
            "",
            metadata={"tty": where.tty, "tmux_session": where.session, "tmux_window": where.window},
        )
    monkeypatch.setenv("TMUX_PANE", "%7")
    monkeypatch.setattr(self_session, "pane_location", lambda pane: where)
    store.send(_inbox("mine"), "Hello", "claude:sender")

    _run(_parser(), "inbox", "next", "--self")

    assert "Hello" in capsys.readouterr().out


def test_tell_reads_stdin(capsys, monkeypatch):
    _attach("codex:recipient", "recipient")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:sender")
    monkeypatch.setattr(sys, "stdin", io.StringIO("- bullet\nsecond line\n"))

    _run(_parser(), "tell", "recipient", "-")

    assert (
        next(_inbox("recipient").glob("*.md")).read_text().endswith("\n\n- bullet\nsecond line\n")
    )
    capsys.readouterr()


def test_failed_print_restores_message(monkeypatch):
    _attach("codex:mine", "mine")
    monkeypatch.setenv("LEMONAID_CHANNEL", "codex:mine")
    inbox = _inbox("mine")
    store.send(inbox, "Keep me", "claude:sender")

    class BrokenOutput:
        def write(self, text):
            raise BrokenPipeError("closed")

    monkeypatch.setattr(sys, "stdout", BrokenOutput())
    with pytest.raises(BrokenPipeError):
        _run(_parser(), "inbox", "next", "--self")

    assert len(list(inbox.glob("*.md"))) == 1
    assert not list((inbox / "done").glob("*.md"))


def test_failed_read_restores_message(tmp_path, monkeypatch):
    inbox = tmp_path / "messages"
    store.send(inbox, "Keep me", "claude:sender")
    read_text = type(inbox).read_text

    def unreadable(path, *args, **kwargs):
        if path.parent.name == "done":
            raise OSError("unreadable")

        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(type(inbox), "read_text", unreadable)
    with pytest.raises(OSError, match="unreadable"):
        store.take_next(inbox)

    assert len(list(inbox.glob("*.md"))) == 1
    assert not list((inbox / "done").glob("*.md"))


def test_watch_stops_when_attachment_moves_or_timeout(tmp_path):
    inbox = tmp_path / "messages"
    with pytest.raises(ValueError, match="no longer attached"):
        store.watch_next(inbox, lambda: False, interval=0.01)

    with pytest.raises(TimeoutError, match="timeout"):
        store.watch_next(inbox, lambda: True, timeout=0.01, interval=0.01)
