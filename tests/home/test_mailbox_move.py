from pathlib import Path

import pytest

from lemonaid.home import layout
from lemonaid.messages import store


def _old(lemon_id: str = "a1"):
    old = layout.lemons_dir() / "inbox" / lemon_id
    old.mkdir(parents=True)
    return old


def test_the_old_folder_moves_once_and_leaves_a_link_for_older_lemonaids():
    (_old() / "20261101T000000000000Z-hello.md").write_text("Hello.")

    mailbox = store.mailbox_for_id("a1")

    assert mailbox == layout.lemons_dir() / "mailbox" / "a1"
    assert store.take_next(mailbox)[1].endswith("Hello.")
    assert (layout.lemons_dir() / "inbox").resolve() == mailbox.parent.resolve()
    assert store.mailbox_root() == mailbox.parent


def test_a_link_lost_to_an_interrupted_move_is_made_again():
    (layout.lemons_dir() / "mailbox").mkdir(parents=True)

    store.mailbox_for_id("a1")

    assert (layout.lemons_dir() / "inbox").is_symlink()


def test_an_old_folder_beside_the_new_one_stops_every_message_command():
    _old()
    mailbox = store.mailbox_for_id("a1")
    (layout.lemons_dir() / "inbox").unlink()
    _old()  # an older lemonaid wrote to the old path between the move and the link

    with pytest.raises(ValueError, match="both exist"):
        store.mailbox_for_id("a1")
    with pytest.raises(ValueError, match="both exist"):
        store.send(mailbox, "Hello.", "tester")


def test_a_briefs_dir_override_moves_its_old_folder_too(monkeypatch, tmp_path):
    monkeypatch.setenv("LEMONAID_BRIEFS_DIR", str(tmp_path / "briefs"))
    old = tmp_path / "briefs" / "inbox" / "a1"
    old.mkdir(parents=True)
    (old / "20261101T000000000000Z-old.md").write_text("Old.")

    assert store.take_next(store.mailbox_for_id("a1"))[1].endswith("Old.")


def test_another_process_finishing_the_move_first_leaves_one_mailbox(monkeypatch):
    (_old() / "20261101T000000000000Z-old.md").write_text("Old.")
    old, new = layout.lemons_dir() / "inbox", layout.lemons_dir() / "mailbox"
    rename = Path.rename

    def another_process_first(path, target):
        if path == old and not new.exists():
            rename(old, new)
            old.symlink_to("mailbox")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", another_process_first)

    assert store.take_next(store.mailbox_for_id("a1"))[1].endswith("Old.")


def test_a_folder_that_cannot_be_moved_stops_message_commands(monkeypatch):
    _old()
    old = layout.lemons_dir() / "inbox"
    rename = Path.rename

    def cannot_move(path, target):
        if path == old:
            raise PermissionError(f"cannot move {old}")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", cannot_move)

    with pytest.raises(PermissionError):
        store.mailbox_for_id("a1")
    monkeypatch.setattr(Path, "rename", rename)
    assert not (layout.lemons_dir() / "mailbox").exists()
