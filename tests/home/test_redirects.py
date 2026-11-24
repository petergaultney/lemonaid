import sys

import pytest

from lemonaid import cli
from lemonaid.brief import store
from lemonaid.home import redirects
from lemonaid.messages import store as messages

_STORAGE = (
    "LEMONAID_DB",
    "LEMONAID_STATE_DIR",
    "LEMONAID_LEMONS_DIR",
    "LEMONAID_LEGACY_BRIEFS_DIR",
    "LEMONAID_BRIEFS_DIR",
    "LEMONAID_MESSAGES_DIR",
)


@pytest.fixture
def home(monkeypatch, tmp_path):
    """A home with none of lemonaid's storage redirected."""
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in _STORAGE:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def _sandbox(monkeypatch, home, *names: str) -> None:
    for name in ("LEMONAID_DB", "LEMONAID_STATE_DIR", *names):
        monkeypatch.setenv(name, str(home / "sandbox" / name.lower()))


def test_a_home_redirected_whole_or_not_at_all_runs(home, monkeypatch):
    assert redirects.partial() == ""

    _sandbox(monkeypatch, home, "LEMONAID_LEMONS_DIR")

    assert redirects.partial() == ""


def test_explicit_brief_and_mailbox_folders_redirect_both(home, monkeypatch):
    _sandbox(monkeypatch, home, "LEMONAID_BRIEFS_DIR", "LEMONAID_MESSAGES_DIR")

    assert redirects.partial() == ""


def test_a_database_and_state_redirected_without_the_briefs_is_refused(home, monkeypatch):
    _sandbox(monkeypatch, home)

    why = redirects.partial()

    assert why.startswith("lemonaid won't run with only part of its storage redirected.")
    assert "Redirected: the database (" in why
    assert f"Not redirected: the briefs ({home / '.lemons' / 'brief'})" in why


def test_redirected_mailboxes_alone_leave_the_briefs_live(home, monkeypatch):
    _sandbox(monkeypatch, home, "LEMONAID_MESSAGES_DIR")

    assert f"Not redirected: the briefs ({home / '.lemons' / 'brief'})." in redirects.partial()


def test_a_redirected_new_home_before_cutover_leaves_the_old_home_live(home, monkeypatch):
    (home / ".brief-lemons").mkdir()
    _sandbox(monkeypatch, home, "LEMONAID_LEMONS_DIR")

    assert f"Not redirected: the briefs ({home / '.brief-lemons'}) and the mailboxes (" in (
        redirects.partial()
    )


@pytest.mark.parametrize(
    "names",
    [(), ("LEMONAID_LEMONS_DIR",), ("LEMONAID_BRIEFS_DIR",), ("LEMONAID_MESSAGES_DIR",)],
)
def test_the_folders_judged_are_the_ones_the_stores_use(home, monkeypatch, names):
    _sandbox(monkeypatch, home, *names)

    assert redirects._briefs() == store.briefs_dir()
    assert redirects._mailboxes() == messages.mailbox_root()


def test_a_variable_naming_its_default_redirects_nothing(home, monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", str(home / ".local" / "share" / "lemonaid" / "lemonaid.db"))

    assert redirects.partial() == ""


def test_a_command_in_a_partly_redirected_home_exits_before_doing_anything(
    home, monkeypatch, capsys
):
    monkeypatch.setenv("LEMONAID_DB", str(home / "sandbox.db"))
    monkeypatch.setattr(sys, "argv", ["lemonaid", "config", "path"])

    with pytest.raises(SystemExit) as stop:
        cli.main()

    printed = capsys.readouterr()
    assert stop.value.code == 1 and printed.out == ""
    assert "only part of its storage redirected" in printed.err
