"""Day and week snoozes count mornings; the picker labels and config presets follow."""

import asyncio
import time
from datetime import datetime
from datetime import time as clock

import pytest
from textual.app import App
from textual.widgets import OptionList

from lemonaid import config
from lemonaid.inbox.snooze_time import describe, parse_wake
from lemonaid.inbox.tui.screens import SnoozeScreen

NINE = clock(9, 0)
FRIDAY = (2026, 10, 2)


def _at(hour: int, minute: int = 0) -> float:
    return datetime(*FRIDAY, hour, minute).timestamp()


def _wake(text: str, now: float, day_start: clock = NINE) -> datetime:
    wake = parse_wake(text, now, day_start)
    assert wake is not None
    return datetime.fromtimestamp(wake)


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (2, 0, datetime(*FRIDAY, 9)),
        (8, 59, datetime(*FRIDAY, 9)),
        (9, 0, datetime(2026, 10, 3, 9)),
        (9, 1, datetime(2026, 10, 3, 9)),
        (23, 0, datetime(2026, 10, 3, 9)),
    ],
)
def test_one_day_is_the_next_start_of_day(hour, minute, expected):
    assert _wake("1d", _at(hour, minute)) == expected
    assert _wake("morning", _at(hour, minute)) == expected


def test_n_days_count_mornings_on_both_sides_of_the_start_of_day():
    assert _wake("4d", _at(2)) == datetime(2026, 10, 5, 9)
    assert _wake("4d", _at(14)) == datetime(2026, 10, 6, 9)


def test_a_week_is_seven_mornings():
    assert _wake("1w", _at(14)) == _wake("7d", _at(14)) == datetime(2026, 10, 9, 9)
    assert _wake("1w", _at(2)) == datetime(2026, 10, 8, 9)


def test_a_fraction_of_a_day_rounds_up_to_whole_mornings():
    assert _wake("1.5d", _at(14)) == _wake("2d", _at(14))


def test_under_a_day_is_exact_whatever_the_unit():
    assert _wake("0.5d", _at(14)) == datetime(2026, 10, 3, 2)
    assert _wake("36h", _at(14)) == datetime(2026, 10, 4, 2)
    assert _wake("30m", _at(23, 45)) == datetime(2026, 10, 3, 0, 15)


@pytest.fixture
def new_york(monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.mark.parametrize("start", [datetime(2026, 3, 8, 1, 30), datetime(2026, 11, 1, 0, 30)])
def test_exact_durations_keep_their_length_across_daylight_saving(new_york, start):
    now = start.timestamp()
    assert parse_wake("2h", now, NINE) == now + 7200
    assert parse_wake("0.5d", now, NINE) == now + 43200


def test_day_snoozes_end_at_the_start_of_day_across_daylight_saving(new_york):
    assert _wake("1d", datetime(2026, 3, 7, 23).timestamp()) == datetime(2026, 3, 8, 9)


def test_the_start_of_day_is_a_parameter():
    assert _wake("1d", _at(14), clock(7, 30)) == datetime(2026, 10, 3, 7, 30)


def test_labels_say_how_long_and_when_day_snoozes_end():
    assert describe("30m", _at(14), NINE) == "30 minutes"
    assert describe("1h", _at(14), NINE) == "1 hour"
    assert describe("1d", _at(14), NINE) == "Tomorrow morning, Sat 09:00"
    assert describe("1d", _at(2), NINE) == "This morning, Fri 09:00"
    assert describe("4d", _at(14), NINE) == "4 days, Tue 09:00"
    assert describe("1w", _at(14), NINE) == "1 week, Fri 09:00"


def _labels(screen: SnoozeScreen) -> list[str]:
    labels: list[str] = []

    async def run() -> None:
        app = App()
        async with app.run_test() as pilot:
            app.push_screen(screen)
            await pilot.pause()
            options = app.screen.query_one("#snooze-options", OptionList)
            labels.extend(
                str(options.get_option_at_index(i).prompt) for i in range(options.option_count)
            )

    asyncio.run(run())
    return labels


def test_the_picker_lists_the_presets_it_is_given():
    labels = _labels(SnoozeScreen(presets=("10m", "2w"), day_start=NINE))
    assert labels[0] == "10 minutes"
    assert labels[1].startswith("2 weeks, ")


def test_config_presets_and_start_of_day(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text(
        '[inbox]\nsnooze_presets = ["15m", "soon", "2w"]\nsnooze_day_starts = "08:00"\n'
    )
    inbox = config.load_config(path).inbox
    assert inbox.snooze_presets == ("15m", "2w")
    assert inbox.snooze_day_starts == clock(8, 0)
    assert "'soon'" in capsys.readouterr().err


def test_config_refuses_a_start_of_day_with_an_offset(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text('[inbox]\nsnooze_day_starts = "09:00+00:00"\n')
    day_start = config.load_config(path).inbox.snooze_day_starts
    assert day_start == NINE
    assert parse_wake("1d", _at(14), day_start) is not None
    assert "not a local HH:MM" in capsys.readouterr().err


def test_config_defaults_and_an_empty_list(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[inbox]\n")
    assert config.load_config(path).inbox.snooze_presets == ("30m", "3h", "1d", "4d")
    assert config.load_config(path).inbox.snooze_day_starts == NINE
    path.write_text("[inbox]\nsnooze_presets = []\n")
    assert config.load_config(path).inbox.snooze_presets == ("30m", "3h", "1d", "4d")
