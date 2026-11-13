"""Toggle a PO box, tell to it, and receive through `mailbox next`, end to end on one machine."""

import argparse
import datetime
from pathlib import Path

import pytest

import lemonaid.brief.cli
import lemonaid.messages.cli
import lemonaid.po_box.cli
from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.config import load_config
from lemonaid.inbox import db
from lemonaid.messages import store
from lemonaid.po_box import enrollment, inbox

from . import shared


@pytest.fixture(autouse=True)
def _no_inherited_session_identity(monkeypatch):
    for name in ("LEMONAID_CHANNEL", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "TMUX_PANE"):
        monkeypatch.delenv(name, raising=False)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    lemonaid.messages.cli.add_tell_parser(subparsers)
    lemonaid.messages.cli.setup_parser(subparsers)
    lemonaid.po_box.cli.setup_parser(subparsers)
    lemonaid.brief.cli.setup_parser(subparsers)
    return parser


def _run(*arguments: str) -> None:
    args = _parser().parse_args(arguments)
    args.func(args)


def _attach(channel: str, name: str, header: str = "") -> tuple[str, Path]:
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{header}# {name} work\n")
    with db.connect() as conn:
        db.add(conn, channel, "", metadata={})
        attached.attach(conn, channel, path)
        return identity.ensure(conn, path), path


def _watcher_pass(lemon_id: str, brief: Path) -> None:
    enrollment.sync(
        load_config().po_box,
        brief,
        store.mailbox_for_id(lemon_id),
        datetime.datetime.now(datetime.UTC),
    )


def test_a_lemon_with_a_po_box_receives_a_message_labeled_as_from_afar(
    capsys, monkeypatch, tmp_path
):
    root = shared.configure_po_box(monkeypatch, tmp_path)
    recipient, brief = _attach("claude:recipient", "recipient", "---\narea: lemonaid\n---\n")
    _attach("claude:sender", "sender")

    _run("brief", "po-box", "--channel", "claude:recipient")
    _watcher_pass(recipient, brief)
    capsys.readouterr()

    _run("po-box", "list")
    assert capsys.readouterr().out == f"sam/{recipient}\tlemonaid\trecipient work\n"

    _run("tell", "--channel", "claude:sender", f"sam/{recipient}", "Can you check the PR?")
    sent = capsys.readouterr().out.strip()
    assert (root / "lemons" / "sam" / recipient / "inbox" / f"{sent}.md").is_file()

    _run("mailbox", "next", "--self", "--channel", "claude:recipient")
    output = capsys.readouterr().out
    assert output.startswith(inbox.LABEL) and "From: sam: " in output
    assert output.endswith("Can you check the PR?\n")
    assert (store.mailbox_for_id(recipient) / "done" / f"{sent}.md").is_file()

    with pytest.raises(SystemExit, match="1"):
        _run("mailbox", "next", "--self", "--channel", "claude:recipient")


def test_turning_the_toggle_off_moves_unread_mail_home(capsys, monkeypatch, tmp_path):
    root = shared.configure_po_box(monkeypatch, tmp_path)
    recipient, brief = _attach("claude:recipient", "recipient")
    _run("brief", "po-box", "--channel", "claude:recipient")
    _watcher_pass(recipient, brief)
    _run("tell", f"sam/{recipient}", "Still unread")
    capsys.readouterr()

    _run("brief", "po-box", "--off", "--channel", "claude:recipient")
    _watcher_pass(recipient, brief)

    assert not (root / "lemons" / "sam" / recipient).exists()
    assert store.pending_count(store.mailbox_for_id(recipient)) == 1
    with pytest.raises(SystemExit, match="1"):
        _run("tell", f"sam/{recipient}", "Too late")
    assert "No lemon has a PO box" in capsys.readouterr().err
