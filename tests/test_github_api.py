import json
import subprocess
import threading
import time

import pytest

from lemonaid.watch import github_api

_BODY = json.dumps({"data": {"repository": {"name": "r"}}})


def _headers(remaining: int, reset: float) -> str:
    return (
        "HTTP/2.0 200 OK\r\n"
        "X-Ratelimit-Limit: 5000\r\n"
        f"X-Ratelimit-Remaining: {remaining}\r\n"
        f"X-Ratelimit-Reset: {int(reset)}\r\n"
        "\r\n"
    )


@pytest.fixture
def gh(monkeypatch):
    monkeypatch.setattr(github_api, "_JITTER", 0)
    replies, calls = [], []

    def run(argv, **kwargs):
        calls.append(argv)
        returncode, stdout, stderr = replies.pop(0)
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    monkeypatch.setattr(github_api.subprocess, "run", run)
    return replies, calls


def test_a_read_returns_data_with_or_without_headers(gh):
    replies, _ = gh
    replies.extend([(0, _headers(4000, time.time() + 600) + _BODY, ""), (0, _BODY, "")])

    assert github_api.graphql([], "{}") == {"repository": {"name": "r"}}
    assert github_api.graphql([], "{}") == {"repository": {"name": "r"}}
    assert github_api.paused() is None


def test_a_quota_refusal_pauses_every_reader_until_the_reset(gh):
    replies, calls = gh
    reset = time.time() + 600
    replies.append(
        (1, _headers(0, reset) + '{"errors": []}', "GraphQL: API rate limit already exceeded")
    )

    assert github_api.graphql([], "{}") is None
    assert github_api.paused() == github_api.Pause(int(reset), "quota")
    assert github_api.graphql([], "{}") is None
    assert len(calls) == 1
    assert github_api.paused(now=reset + 1) is None


def test_nearly_spent_quota_pauses_after_returning_the_read(gh):
    replies, _ = gh
    reset = time.time() + 600
    replies.append((0, _headers(github_api._RESERVE - 1, reset) + _BODY, ""))

    assert github_api.graphql([], "{}") == {"repository": {"name": "r"}}
    assert github_api.paused() == github_api.Pause(int(reset), "quota")


def test_a_secondary_limit_pauses_for_retry_after(gh):
    replies, _ = gh
    replies.append(
        (
            1,
            "HTTP/2.0 403 Forbidden\nRetry-After: 120\n\n{}",
            "You have exceeded a secondary rate limit",
        )
    )

    assert github_api.graphql([], "{}") is None
    pause = github_api.paused()
    assert pause and pause.reason == "secondary"
    assert 100 < pause.until - time.time() <= 120


def test_a_network_failure_does_not_pause(gh):
    replies, _ = gh
    replies.append((1, "", "error connecting to api.github.com"))

    assert github_api.graphql([], "{}") is None
    assert github_api.paused() is None


def test_a_shorter_pause_written_concurrently_never_cuts_a_longer_one_short(monkeypatch):
    write, entered, release = github_api.cursors.write_json, threading.Event(), threading.Event()

    def slow_write(path, value):
        if value["reason"] == "secondary":
            entered.set()
            release.wait(5)
        write(path, value)

    monkeypatch.setattr(github_api.cursors, "write_json", slow_write)
    now = time.time()
    short = threading.Thread(
        target=github_api._pause, args=(github_api.Pause(now + 60, "secondary"),)
    )
    long = threading.Thread(target=github_api._pause, args=(github_api.Pause(now + 3600, "quota"),))
    short.start()
    assert entered.wait(5)
    long.start()
    time.sleep(0.2)  # the longer pause is now waiting for the lock
    release.set()
    short.join(5)
    long.join(5)

    assert github_api._saved() == github_api.Pause(now + 3600, "quota")
