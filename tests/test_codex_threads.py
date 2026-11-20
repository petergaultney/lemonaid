"""Codex answers what it has stored about threads, from the service's snapshot or a
short-lived app-server."""

import json
import subprocess
import sys
import threading
import time

import pytest

from lemonaid.codex import app_server, service, snapshot, stored, threads
from lemonaid.watch import scout_start

_ASK = threads._ask  # conftest stubs it for every other test

_LIVE = "01a1f3b9-8daa-76a1-baa0-9a9ce97ef69f"
_UNKNOWN = "01a0afc2-0344-77c2-b058-000000000000"
_NO_ROLLOUT = "019c2430-eae9-7560-aa54-c5582d4c81ec"
_ARCHIVED = "01a0afc2-0344-77c2-b058-81b023b7b5a4"
_ODD = "01a1c6eb-7681-7f12-a720-eaaf968d7ba2"  # Codex errors in a way it doesn't explain

# A stand-in `codex app-server`: answers from the JSON in $FAKE_CODEX, two archived
# threads per `thread/list` page so the listing is paged.
_FAKE = """
import json, os, sys, time
plan = json.load(open(os.environ["FAKE_CODEX"]))
if plan.get("exit"):
    sys.exit(1)
archived = plan.get("archived", [])
for line in sys.stdin:
    message = json.loads(line)
    method, id = message["method"], message.get("id")
    if method == "initialized" or plan.get("hang"):
        continue
    if method == "initialize":
        print(json.dumps({"id": id, "result": {"userAgent": "fake"}}), flush=True)
        if plan.get("deaf"):
            time.sleep(60)
        continue
    if method == "thread/list":
        start = int(message["params"]["cursor"] or 0)
        page = archived[start:start + 2]
        more = start + 2 < len(archived)
        result = {"data": [{"id": t} for t in page], "nextCursor": str(start + 2) if more else None}
    else:
        thread = message["params"]["threadId"]
        if error := plan["errors"].get(thread):
            print(json.dumps({"id": id, "error": {"code": -32600, "message": error}}), flush=True)
            continue
        if method == "thread/read":
            result = {"thread": {"id": thread, "cwd": "/work", "name": "Review #1", "updatedAt": 7}}
        else:
            result = {"data": [{}], "nextCursor": None}
    print(json.dumps({"method": "noise/elsewhere", "params": {}}), flush=True)
    print(json.dumps({"id": id, "result": result}), flush=True)
"""


@pytest.fixture
def codex(tmp_path, monkeypatch):
    """Put a fake `codex` on PATH, answering from the plan that the test passes in."""
    monkeypatch.setattr(threads, "_ask", _ASK)
    monkeypatch.delenv(app_server.NO_APP_SERVER)
    binary = tmp_path / "bin" / "codex"
    binary.parent.mkdir()
    binary.write_text(f"#!{sys.executable}\nimport sys; sys.argv[1:] = []\n{_FAKE}")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary.parent))

    def plan(**answers):
        (tmp_path / "plan.json").write_text(json.dumps({"errors": {}, **answers}))
        monkeypatch.setenv("FAKE_CODEX", str(tmp_path / "plan.json"))

    return plan


_PLAN = {
    "archived": ["a", "b", "c", _ARCHIVED],
    "errors": {
        _UNKNOWN: f"thread not loaded: {_UNKNOWN}",
        _NO_ROLLOUT: f"invalid paginated history lineage for {_NO_ROLLOUT}: missing source rollout",
        _ODD: "database is locked",
    },
}


def _thread(thread: str, archived: bool = False) -> stored.Thread:
    return stored.Thread(thread, "/work", "Review #1", "", "", "", 7, archived)


def test_codex_answers_and_leaves_out_threads_it_cannot_explain(codex):
    codex(**_PLAN)

    assert threads.get([_LIVE, _UNKNOWN, _NO_ROLLOUT, _ARCHIVED, _ODD, ""]) == {
        _LIVE: _thread(_LIVE),
        _UNKNOWN: None,
        _NO_ROLLOUT: None,
        _ARCHIVED: _thread(_ARCHIVED, archived=True),
    }


def test_gone_counts_blank_unknown_archived_and_lost_threads(monkeypatch):
    monkeypatch.setattr(
        threads,
        "_ask",
        lambda missing: {
            _LIVE: _thread(_LIVE),
            _UNKNOWN: None,
            _ARCHIVED: _thread(_ARCHIVED, True),
        },
    )

    assert threads.gone([_LIVE, _UNKNOWN, _ARCHIVED, _ODD, ""]) == {_UNKNOWN, _ARCHIVED, ""}


@pytest.mark.parametrize("failure", [{"exit": True}, {"hang": True}, None])
def test_a_codex_that_cannot_be_asked_counts_nothing_as_gone(codex, tmp_path, monkeypatch, failure):
    if failure is None:
        monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    else:
        codex(**failure)
    monkeypatch.setattr(threads, "_TIMEOUT", 0.5)

    assert threads.get([_LIVE, _UNKNOWN]) == {}
    assert threads.gone([_LIVE, _UNKNOWN, ""]) == {""}


def test_a_codex_that_stops_reading_its_input_cannot_outlast_the_deadline(codex, monkeypatch):
    """Many more requests than a pipe holds, to a Codex that stops reading after starting."""
    codex(deaf=True)
    monkeypatch.setattr(threads, "_TIMEOUT", 0.5)
    started: list[subprocess.Popen] = []
    popen = subprocess.Popen

    def recording(*args, **kwargs):
        started.append(popen(*args, **kwargs))
        return started[-1]

    monkeypatch.setattr(subprocess, "Popen", recording)
    batch = [f"01a1f3b9-8daa-76a1-baa0-{n:012x}" for n in range(5000)]

    begun = time.monotonic()
    assert threads.get(batch) == {}
    assert time.monotonic() - begun < 3
    assert [proc.returncode is not None for proc in started] == [True]


def test_the_snapshot_answers_without_starting_codex_and_records_the_question(monkeypatch):
    monkeypatch.setattr(threads, "_ask", lambda missing: pytest.fail(f"asked for {missing}"))
    monkeypatch.setattr(scout_start, "ensure_host", lambda: pytest.fail("started a host"))
    snapshot.write({_LIVE: _thread(_LIVE), _UNKNOWN: None})

    assert threads.gone([_LIVE, _UNKNOWN]) == {_UNKNOWN}
    assert snapshot.interest().keys() == {_LIVE, _UNKNOWN}


def test_a_thread_the_snapshot_lacks_is_asked_and_starts_the_host(monkeypatch):
    hosts: list[None] = []
    monkeypatch.setattr(scout_start, "ensure_host", lambda: hosts.append(None))
    monkeypatch.setattr(threads, "_ask", lambda missing: {thread: None for thread in missing})
    snapshot.write({_LIVE: _thread(_LIVE)})

    assert threads.get([_LIVE, _UNKNOWN]) == {_LIVE: _thread(_LIVE), _UNKNOWN: None}
    assert hosts == [None]


def test_the_service_keeps_one_server_and_refreshes_what_was_asked(codex):
    codex(**_PLAN)
    state = service._State()

    service._refresh(state, {_LIVE, _UNKNOWN, _ODD})
    first = state.server
    service._refresh(state, {_LIVE, _UNKNOWN, _ODD})

    assert first is not None and state.server is first and first.alive()
    assert snapshot.read() == {_LIVE: _thread(_LIVE), _UNKNOWN: None}
    assert state.tried == {_LIVE, _UNKNOWN, _ODD}
    first.close()


def test_the_service_replaces_a_server_that_died(codex):
    codex(**_PLAN)
    state = service._State()
    service._refresh(state, {_LIVE})
    assert state.server is not None
    state.server.close()

    service._refresh(state, {_LIVE})

    assert state.server is not None and state.server.alive()
    state.server.close()


def test_the_service_refreshes_early_only_for_a_thread_it_has_not_read(monkeypatch):
    refreshed: list[set[str]] = []
    monkeypatch.setattr(service, "_refresh", lambda state, asked: refreshed.append(asked))
    state = service._State(refreshed=time.time(), tried={_LIVE})
    snapshot.interested([_LIVE])

    assert service.tick(state, threading.Event()) == 1
    state.looked = 0.0
    snapshot.interested([_UNKNOWN])
    service.tick(state, threading.Event())
    assert state.worker is not None
    state.worker.join()

    assert refreshed == [{_LIVE, _UNKNOWN}]


def test_a_stale_snapshot_answers_nothing(monkeypatch):
    snapshot.write({_UNKNOWN: None})
    monkeypatch.setattr(snapshot, "STALE", -1.0)

    assert snapshot.read() == {}


def test_an_unavailable_codex_does_not_keep_restarting_the_host(monkeypatch):
    monkeypatch.setattr(app_server, "start", lambda timeout: None)
    snapshot.interested([_LIVE])
    running = service.service()

    assert running.tick(threading.Event()) == 1
    running.join()

    assert not running.pending()
