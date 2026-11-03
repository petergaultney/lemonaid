from lemonaid import pr_states
from lemonaid.inbox.tui.rows import pr_numbers

from .shared import table


def test_merged_prs_do_not_count_toward_the_cutoff():
    text = table(11, 12, 13)
    assert pr_numbers.brief_numbers(text) == ()
    pr_states.record("owner/repo", "11", "MERGED")
    assert [pr.number for pr in pr_numbers.brief_numbers(text)] == ["12", "13"]
    assert pr_numbers.brief_numbers(table(11, 12, 13, 14)) == ()
    pr_states.record("owner/repo", "13", "CLOSED")
    assert [pr.number for pr in pr_numbers.brief_numbers(text)] == ["12"]


def test_cache_sees_a_merge_without_the_brief_changing(tmp_path):
    path = tmp_path / "brief.md"
    path.write_text(table(1, 2, 3))
    cache = pr_numbers.Cache()
    assert cache.brief(path) == ()
    pr_states.record("owner/repo", "2", "MERGED")
    assert [pr.number for pr in cache.brief(path)] == ["1", "3"]


def test_state_is_per_repo():
    pr_states.record("other/repo", "11", "MERGED")
    assert not pr_states.is_finished("owner/repo", "11")
