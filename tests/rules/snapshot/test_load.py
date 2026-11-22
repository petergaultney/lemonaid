import datetime as dt

from lemonaid.rules import patterns, snapshot
from tests.rules import shared

_NOW = dt.datetime(2026, 11, 22, 16, 0, tzinfo=dt.UTC)


def test_what_was_promoted_loads_unchanged(tmp_path):
    source = shared.write(tmp_path, shared.MERGE_ASK, shared.REVIEWER_ASK)
    promoted = patterns.load(source).patterns

    snapshot.promote(source, promoted, _NOW)

    assert snapshot.load(source) == promoted


def test_nothing_loads_before_a_promote(tmp_path):
    assert snapshot.load(shared.write(tmp_path, shared.MERGE_ASK)) == []


def test_patterns_promoted_from_another_file_do_not_load(tmp_path):
    source = shared.write(tmp_path / "a", shared.MERGE_ASK)
    snapshot.promote(source, patterns.load(source).patterns, _NOW)

    assert snapshot.load(shared.write(tmp_path / "b", shared.MERGE_ASK)) == []


def test_editing_the_pattern_file_changes_nothing_until_the_next_promote(tmp_path):
    source = shared.write(tmp_path, shared.MERGE_ASK)
    snapshot.promote(source, patterns.load(source).patterns, _NOW)

    source.write_text("[[pattern]\nhalf-saved")

    assert [pattern.id for pattern in snapshot.load(source)] == ["merge-ask"]
