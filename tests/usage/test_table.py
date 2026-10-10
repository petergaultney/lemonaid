from lemonaid.usage import settings, table

from .shared import MID, WINDOW_S, sample

_CONFIG = settings.UsageConfig()


def test_rows_are_worst_pace_first_with_unjudgeable_last():
    current = {
        "a": sample(40),
        "b": sample(80),
        "c": sample(5, WINDOW_S * 1.49),  # 1% elapsed: too early to judge
    }

    assert [r.window for r in table.rows(current, MID, _CONFIG)] == ["b", "a", "c"]


def test_row_carries_usage_and_pace():
    [row] = table.rows({"a": sample(60)}, MID, _CONFIG)

    assert (row.used_percent, row.pace) == (60, 1.2)
