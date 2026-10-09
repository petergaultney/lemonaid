"""`[brief] name` names new lemons, and rerolls, with a command instead of a WordyBin."""

import datetime

import pytest

from lemonaid.brief import identity, names, reroll, store
from lemonaid.config import get_config_path
from lemonaid.inbox import db


def _name_command(command: str) -> None:
    get_config_path().write_text(f"[brief]\nname = '''{command}'''\n")


def test_a_configured_command_names_a_new_brief():
    _name_command("echo Marvin")

    path = store.create("A lemon", datetime.date(2026, 10, 8))

    assert identity.from_path(path) == "a-lemon.Marvin"


def test_a_name_another_lemon_holds_is_asked_for_again(tmp_path):
    counter = tmp_path / "count"
    _name_command(f"echo x >> {counter}; echo Robot$(wc -l < {counter} | tr -d ' ')")
    first = store.create("same slug", datetime.date(2026, 10, 7))
    second = store.create("same slug", datetime.date(2026, 10, 8))
    second.write_text("# same slug\n\nBrief-ID: same-slug.Robot1\n")
    with db.connect() as conn:
        identity.ensure(conn, first, regenerate_on_collision=True)
        identity.ensure(conn, second, regenerate_on_collision=True)

    assert identity.from_path(first) == "same-slug.Robot1"
    assert identity.from_path(second) == "same-slug.Robot3"


@pytest.mark.parametrize(
    ("command", "error"),
    [
        ("exit 1", "printed no name"),
        ("true", "printed no name"),
        ("echo bad.name", "letters, digits"),
        ('echo "it\'s"', "letters, digits"),
    ],
)
def test_a_failing_command_or_unsafe_name_creates_no_brief(command, error):
    _name_command(command)

    with pytest.raises(ValueError, match=error):
        store.create("A lemon", datetime.date(2026, 10, 8))

    assert not list(store.briefs_dir().glob("*.md"))


def test_set_takes_any_safe_name_as_written_when_a_command_is_configured():
    _name_command("echo Marvin")
    path = store.create("center", datetime.date(2026, 10, 8))
    with db.connect() as conn:
        identity.ensure(conn, path)

        assert reroll.reroll(conn, path, "hal-9000").new_id == "center.hal-9000"
        with pytest.raises(ValueError, match="letters, digits"):
            reroll.reroll(conn, path, "hal.9000")


def test_without_a_command_set_still_wants_a_wordybin():
    assert names.chosen("quickodd") == "QuickOdd"
    with pytest.raises(ValueError, match="two-word WordyBin"):
        names.chosen("Quick")
