"""Live PR state for the PRs a brief names."""

import threading
from pathlib import Path

from lemonaid.brief import pr


def test_refs_keep_the_order_written_so_the_limit_drops_the_last():
    text = (
        "PR #74 now. Earlier: https://github.com/o/r/pull/1 https://github.com/o/r/pull/2 "
        "https://github.com/o/r/pull/3"
    )

    assert pr.refs(text) == ["74", "https://github.com/o/r/pull/1", "https://github.com/o/r/pull/2"]


def test_the_same_number_in_two_repositories_is_two_prs():
    text = "https://github.com/o/a/pull/74 https://github.com/o/b/pull/74 PR #74"
    found = pr.refs(text)

    assert found == ["https://github.com/o/a/pull/74", "https://github.com/o/b/pull/74", "74"]
    assert [pr.label(ref, found) for ref in found] == ["a#74", "b#74", "#74"]


def test_a_bare_number_is_the_urls_pr_when_every_url_is_in_one_repository():
    text = "PR #74 is up: https://github.com/o/r/pull/74. Also PR #75, pr#76, PR #77 and issue #9."

    assert pr.refs(text) == ["https://github.com/o/r/pull/74", "75", "76"]
    assert [pr.label(ref) for ref in pr.refs(text)] == ["#74", "#75", "#76"]


def test_the_configured_command_gets_the_quoted_ref_in_the_places_directory(tmp_path):
    (tmp_path / "marker").touch()
    command = """[ -f marker ] && [ {ref} = 'https://x/o/r/pull/1 x' ] && echo MERGED extra"""

    assert pr.lookup(command, "https://x/o/r/pull/1 x", tmp_path) == "merged"


def test_anything_but_a_state_word_shows_nothing(tmp_path):
    assert pr.lookup("echo pending", "74", tmp_path) == ""
    assert pr.lookup("echo open; exit 1", "74", tmp_path) == ""
    assert pr.lookup("true", "74", Path("/no/such/dir")) == ""


def test_an_unset_command_runs_nothing():
    assert pr.configured("  ") is pr.no_state
    assert pr.configured("echo draft")("74", None) == "draft"


def test_cache_answers_immediately_and_fills_in_the_background():
    release = threading.Event()
    fetched: list[str] = []

    def fetch(ref: str, cwd: Path | None) -> str:
        release.wait(5)
        fetched.append(ref)
        return "merged"

    cache = pr.Cache(fetch)

    assert cache.get("74", None) == ""
    assert cache.get("74", None) == ""  # one fetch in flight, not two
    release.set()
    for thread in threading.enumerate():
        if thread is not threading.current_thread() and thread.daemon:
            thread.join(5)

    assert cache.get("74", None) == "merged"
    assert fetched == ["74"]


def test_a_leading_bare_ref_keeps_its_place_when_its_url_comes_later():
    text = (
        "PR #74 now. https://github.com/o/r/pull/1 https://github.com/o/r/pull/2 "
        "https://github.com/o/r/pull/3 https://github.com/o/r/pull/74"
    )

    assert pr.refs(text) == [
        "https://github.com/o/r/pull/74",
        "https://github.com/o/r/pull/1",
        "https://github.com/o/r/pull/2",
    ]
