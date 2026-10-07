from lemonaid.config import PlaceRoot
from lemonaid.inbox.tui import pr_numbers


def test_maps_are_per_root_cached_and_single_flight(tmp_path):
    roots = [
        PlaceRoot(tmp_path / "one", open_prs="lookup"),
        PlaceRoot(tmp_path / "two", open_prs="lookup"),
    ]
    cache = pr_numbers.Cache()
    assert cache.due([*roots, roots[0], PlaceRoot(tmp_path / "unset")], 0) == roots
    assert cache.due(roots, 200) == []
    cache.store(roots[0], {"topic": pr_numbers.PR("1")}, 1)
    cache.store(roots[1], {"topic": pr_numbers.PR("2")}, 1)
    assert cache.number(roots[0], "topic") == pr_numbers.PR("1")
    assert cache.number(roots[1], "topic") == pr_numbers.PR("2")
    assert cache.due(roots, 180) == []
    assert cache.due(roots, 181) == roots
    cache.store(roots[0], {}, 182)
    assert cache.number(roots[0], "topic") is None


def test_brief_cache_updates_and_forgets_deleted_files(tmp_path):
    path = tmp_path / "brief.md"
    path.write_text("## Now\n### PRs\nbroken\n")
    cache = pr_numbers.Cache()
    assert cache.brief(path) is None
    path.write_text("## Now\n### Next\n- work\n")
    assert cache.brief(path) is None
    path.unlink()
    assert cache.brief(path) is None


def test_hook_parsing_and_ambiguous_branches():
    assert pr_numbers.branch_map(
        [
            "topic 12",
            "topic 012",
            "other 99",
            "other 100",
            "malformed",
            "bad 0",
            "bad -1",
            "bad nope",
            "bad \uff11\uff12",
            "bad 1 extra",
        ]
    ) == {"topic": pr_numbers.PR("12")}


def test_hook_runs_in_root_and_failure_clears(tmp_path):
    root = PlaceRoot(tmp_path, open_prs="printf 'topic 12\\nother 99\\n'")
    assert pr_numbers.refresh(root) == {"topic": pr_numbers.PR("12"), "other": pr_numbers.PR("99")}
    assert pr_numbers.refresh(PlaceRoot(tmp_path, open_prs="exit 1")) == {}


def test_undecodable_hook_output_is_a_failed_lookup(monkeypatch, tmp_path):
    def bad_output(*args):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")

    monkeypatch.setattr(pr_numbers.hooks, "run_lines", bad_output)
    assert pr_numbers.refresh(PlaceRoot(tmp_path, open_prs="lookup")) == {}


def test_optional_hook_url_and_legacy_lines():
    assert pr_numbers.branch_map(
        [
            "linked 12 https://example.com/pr/12",
            "legacy 13",
            "duplicate 014",
            "duplicate 14 https://example.com/pr/14",
            "conflict 15 https://one.example/pr/15",
            "conflict 15 https://two.example/pr/15",
            "invalid 16 javascript:alert(1)",
            "bad 17 https://[bad",
            "extra 18 https://example.com/pr/18 extra",
        ]
    ) == {
        "linked": pr_numbers.PR("12", "https://example.com/pr/12"),
        "legacy": pr_numbers.PR("13"),
        "duplicate": pr_numbers.PR("14", "https://example.com/pr/14"),
        "conflict": pr_numbers.PR("15"),
    }
