import datetime as dt
import json

from lemonaid.rules import hits

_NOW = 1_800_000_000.0
_HOUR = 3600.0


def _hit(channel: str = "claude:aaaa1111", pattern: str = "merge-ask") -> hits.Hit:
    return hits.Hit(
        channel, pattern, "report", "claude", "/work", "/t.jsonl", "**Ready to merge?**"
    )


def _outcomes() -> list[str]:
    return [json.loads(line)["outcome"] for line in hits.path().read_text().splitlines()]


def test_the_first_match_is_reported_and_logged():
    assert hits.record(_hit(), _NOW, reporting=True) == hits.Outcome(hits.REPORTED, 0)

    [logged] = [json.loads(line) for line in hits.path().read_text().splitlines()]
    assert logged["pattern"] == "merge-ask"
    assert logged["excerpt"] == "**Ready to merge?**"
    assert dt.datetime.fromisoformat(logged["at"]).timestamp() == _NOW


def test_a_lemon_is_reported_once_a_day_per_pattern():
    hits.record(_hit(), _NOW, reporting=True)

    assert hits.record(_hit(), _NOW + 23 * _HOUR, True).outcome == hits.REPEAT
    assert hits.record(_hit(pattern="push-ask"), _NOW + _HOUR, True).outcome == hits.REPORTED
    assert hits.record(_hit(channel="codex:b"), _NOW + _HOUR, True).outcome == hits.REPORTED
    assert hits.record(_hit(), _NOW + 25 * _HOUR, True).outcome == hits.REPORTED


def test_past_twenty_reports_an_hour_matches_are_held_then_counted():
    for number in range(20):
        hits.record(_hit(channel=f"claude:{number}"), _NOW + number, True)

    held = [hits.record(_hit(channel=f"claude:x{n}"), _NOW + 60 + n, True) for n in range(3)]
    after = hits.record(_hit(channel="claude:later"), _NOW + _HOUR + 1, True)

    assert {outcome.outcome for outcome in held} == {hits.HELD}
    assert after == hits.Outcome(hits.REPORTED, 3)
    assert hits.record(_hit(channel="claude:next"), _NOW + _HOUR + 2, True).held == 0


def test_with_nobody_to_report_to_a_match_is_only_logged():
    assert hits.record(_hit(), _NOW, reporting=False) == hits.Outcome(hits.LOGGED, 0)
    assert hits.record(_hit(), _NOW + 1, reporting=True).outcome == hits.REPORTED
    assert _outcomes() == [hits.LOGGED, hits.REPORTED]


def test_a_damaged_line_is_skipped():
    hits.record(_hit(), _NOW, True)
    with hits.path().open("a") as log:
        log.write("not json\n")

    assert hits.record(_hit(), _NOW + 1, True).outcome == hits.REPEAT
