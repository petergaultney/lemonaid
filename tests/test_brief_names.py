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

    assert identity.from_path(path) == "Marvin.a-lemon"


def test_a_name_another_lemon_holds_is_asked_for_again(tmp_path):
    counter = tmp_path / "count"
    _name_command(f"echo x >> {counter}; echo Robot$(wc -l < {counter} | tr -d ' ')")
    first = store.create("same slug", datetime.date(2026, 10, 7))
    second = store.create("same slug", datetime.date(2026, 10, 8))
    second.write_text("# same slug\n\nBrief-ID: Robot1.same-slug\n")
    with db.connect() as conn:
        identity.ensure(conn, first, regenerate_on_collision=True)
        identity.ensure(conn, second, regenerate_on_collision=True)

    assert identity.from_path(first) == "Robot1.same-slug"
    assert identity.from_path(second) == "Robot3.same-slug"


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


def test_set_takes_any_safe_name_with_a_capital_first_letter_when_a_command_is_configured():
    _name_command("echo Marvin")
    path = store.create("center", datetime.date(2026, 10, 8))
    with db.connect() as conn:
        identity.ensure(conn, path)

        assert reroll.reroll(conn, path, "hal-9000").new_id == "Hal-9000.center"
        with pytest.raises(ValueError, match="letters, digits"):
            reroll.reroll(conn, path, "hal.9000")


def test_without_a_command_set_wants_a_five_and_a_three_letter_word():
    assert names.chosen("quickodd") == "QuickOdd"
    assert names.chosen("auditINK") == "AuditInk"
    for bad in ("Quick", "QuickOdds", "Quick0dd", "Quick-Od"):
        with pytest.raises(ValueError, match="five-letter word and a three-letter word"):
            names.chosen(bad)


def test_a_lowercase_name_from_the_command_is_capitalized_and_one_without_a_letter_refused():
    _name_command("echo marvin")
    assert identity.from_path(store.create("A lemon", datetime.date(2026, 10, 8))) == (
        "Marvin.a-lemon"
    )

    _name_command("echo 9000")
    with pytest.raises(ValueError, match="capital letter"):
        store.create("Another lemon", datetime.date(2026, 10, 8))


@pytest.mark.parametrize(
    ("brief_id", "name", "description"),
    [
        ("SkullHen.mc-tars", "SkullHen", "mc-tars"),
        ("mc-tars.SkullHen", "SkullHen", "mc-tars"),
        ("a-lemon.marvin", "marvin", "a-lemon"),
        ("_robot.center", "_robot", "center"),
        ("lemon-0123abcd", "", "lemon-0123abcd"),
    ],
)
def test_split_id_reads_both_orders(brief_id, name, description):
    assert names.split_id(brief_id) == (name, description)
    assert identity.brief_name(brief_id) == name
    assert identity.brief_description(brief_id) == description


def test_markdown_id_keeps_the_order_the_id_is_written_in():
    assert identity.markdown_id("SkullHen.mc-tars") == "**SkullHen**.`mc-tars`"
    assert identity.markdown_id("mc-tars.SkullHen") == "`mc-tars`.**SkullHen**"


def test_a_reroll_refuses_a_name_whose_old_order_id_is_taken():
    path = store.briefs_dir() / "center.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# center\n\nBrief-ID: center.BloodKeg\n")
    other = store.briefs_dir() / "other.md"
    other.write_text("# other\n\nBrief-ID: center.SkullHen\n")
    with db.connect() as conn:
        identity.ensure(conn, path)
        identity.ensure(conn, other)
        with pytest.raises(ValueError, match="another lemon's Lemon-ID"):
            reroll.reroll(conn, path, "SkullHen")
