from lemonaid.config import load_config
from lemonaid.grove.window import usage
from lemonaid.usage import samples

NOW = 1_800_000_000


def test_usage_rows_carry_the_inbox_figures_and_colors_worst_pace_first(monkeypatch):
    week, five = 7 * 24 * 60, 5 * 60
    monkeypatch.setattr(
        samples,
        "current_samples",
        lambda: {
            "claude five_hour": samples.Sample(10, NOW + five * 60 // 2, five),
            "claude seven_day": samples.Sample(60, NOW + week * 60 // 2, week),
        },
    )

    rows = usage.rows(load_config(), NOW)

    assert [r["window"] for r in rows] == ["claude seven_day", "claude five_hour"]
    assert rows[0]["used"] == "60%" and rows[0]["elapsed"] == "50%" and rows[0]["pace"] == "1.20x"
    assert all(r["usedColor"].startswith("#") and r["paceColor"].startswith("#") for r in rows)


def test_unreadable_usage_shows_no_rows(monkeypatch):
    def broken():
        raise OSError("gone")

    monkeypatch.setattr(samples, "current_samples", broken)

    assert usage.rows(load_config(), NOW) == []
