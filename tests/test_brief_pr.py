"""Live PR state for the PRs a brief names."""

import json
import subprocess
import threading
from pathlib import Path

from lemonaid.brief import pr


def test_refs_prefer_urls_and_skip_numbers_they_cover():
    text = "PR #74 is up: https://github.com/o/r/pull/74. Also PR #75, pr#76, PR #77 and issue #9."

    assert pr.refs(text) == ["https://github.com/o/r/pull/74", "75", "76"]
    assert [pr.label(ref) for ref in pr.refs(text)] == ["#74", "#75", "#76"]


def _gh(monkeypatch, stdout: str = "", error: Exception | None = None) -> list[dict]:
    calls: list[dict] = []

    def run(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        if error:
            raise error
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(pr.subprocess, "run", run)
    return calls


def test_lookup_reports_draft_open_merged(monkeypatch, tmp_path):
    for data, expected in (
        ({"state": "OPEN", "isDraft": True}, "draft"),
        ({"state": "OPEN", "isDraft": False}, "open"),
        ({"state": "MERGED", "isDraft": False}, "merged"),
    ):
        calls = _gh(monkeypatch, json.dumps(data))
        assert pr.lookup("74", tmp_path) == expected
        assert calls[0]["argv"][:4] == ["gh", "pr", "view", "74"]
        assert calls[0]["cwd"] == tmp_path


def test_lookup_is_empty_when_gh_cannot_say(monkeypatch):
    _gh(monkeypatch, error=subprocess.CalledProcessError(1, "gh"))
    assert pr.lookup("74", None) == ""

    _gh(monkeypatch, error=FileNotFoundError("gh"))
    assert pr.lookup("74", Path("/no/such/dir")) == ""


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
