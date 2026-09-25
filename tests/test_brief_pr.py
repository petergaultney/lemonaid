"""Live PR state for the PRs a brief names."""

import threading
from pathlib import Path

from lemonaid.brief import pr


def test_refs_prefer_urls_and_skip_numbers_they_cover():
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
