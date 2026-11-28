"""`lemonaid openclaw hook`, as lemonaid's OpenClaw plugin runs it for each event."""

import argparse
import io
import json

import pytest

from lemonaid.inbox import db
from lemonaid.openclaw import failures, hook, plugin_install, sessions
from lemonaid.watch import own_edits

KEY = "agent:main:matrix:channel:!room:example.org"
CHANNEL = sessions.channel(KEY)


@pytest.fixture(autouse=True)
def _row():
    with db.connect() as conn:
        db.add(conn, channel=CHANNEL, message="hi", status="read")


def _hook(monkeypatch, event: str, payload: dict, version: str = "") -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    hook._run(argparse.Namespace(event=event, plugin_version=version))


def _row_now() -> db.Notification:
    with db.connect() as conn:
        found = db.get_by_channel(conn, CHANNEL, unread_only=False)
    assert found is not None
    return found


def test_a_turn_runs_from_its_first_report_until_it_ends(monkeypatch):
    _hook(monkeypatch, "turn", {"session_key": KEY, "run": "r1", "at": 100.0})
    _hook(monkeypatch, "turn", {"session_key": KEY, "run": "r1", "at": 160.0})
    assert (_row_now().turn_at, _row_now().metadata["turn_started_at"]) == (160.0, 100.0)

    _hook(monkeypatch, "turn-end", {"session_key": KEY, "run": "r1", "at": 170.0, "said": "Done"})

    row = _row_now()
    assert (row.turn_at, row.metadata["turn_ended_at"], row.status) == (None, 170.0, "unread")


def test_a_late_report_from_a_run_already_over_doesnt_reopen_it(monkeypatch):
    _hook(monkeypatch, "turn", {"session_key": KEY, "run": "r1", "at": 100.0})
    _hook(monkeypatch, "turn-end", {"session_key": KEY, "run": "r1", "at": 110.0, "said": "Done"})

    _hook(monkeypatch, "turn", {"session_key": KEY, "run": "r1", "at": 111.0})

    assert _row_now().turn_at is None


def test_a_failed_turn_is_kept_for_the_lemon_page(monkeypatch):
    _hook(
        monkeypatch,
        "turn-end",
        {"session_key": KEY, "run": "r1", "at": 5.0, "failed": True, "error": "rate limited"},
    )

    assert failures.read(KEY) == [failures.Failure(5000, "rate limited")]
    assert _row_now().status == "unread"


def test_a_gateway_that_started_runs_no_turns(monkeypatch):
    _hook(monkeypatch, "turn", {"session_key": KEY, "run": "r1", "at": 100.0})

    _hook(monkeypatch, "gateway-start", {"at": 200.0})

    assert _row_now().turn_at is None


def test_a_tool_call_that_changed_a_watched_doc_is_the_lemons_own_edit(monkeypatch, tmp_path):
    doc = tmp_path / "notes.md"
    doc.write_text("before\n")
    writer = f"openclaw-{KEY}"
    own_edits.register(own_edits.root(), writer, doc)
    call = {"session_key": KEY, "tool_use_id": "c1", "tool_input": {"path": str(doc)}}

    _hook(monkeypatch, "tool", {**call, "hook_event_name": "PreToolUse"})
    doc.write_text("after\n")
    _hook(monkeypatch, "tool", {**call, "hook_event_name": "PostToolUse"})

    assert own_edits.transitions(own_edits.root(), writer, doc) != []


def test_a_quiet_push_is_refused(monkeypatch, capsys):
    call = {
        "session_key": KEY,
        "hook_event_name": "PreToolUse",
        "tool_use_id": "c1",
        "tool_input": {"command": "git push -q"},
    }

    with pytest.raises(SystemExit) as stopped:
        _hook(monkeypatch, "tool", call)

    assert stopped.value.code == 2
    assert "without -q/--quiet" in capsys.readouterr().err


def test_a_plugin_from_another_version_is_reported_stale(monkeypatch):
    (plugin_install.root()).mkdir(parents=True)
    (plugin_install.root() / "active").write_text("")

    _hook(monkeypatch, "gateway-start", {"at": 1.0}, version="0.0.1")

    assert plugin_install.status().startswith("stale: the gateway runs the plugin from 0.0.1")

    _hook(monkeypatch, "gateway-start", {"at": 1.0}, version=plugin_install.version())

    assert plugin_install.status().startswith("installed")


def test_the_late_end_of_an_older_turn_neither_ends_the_running_one_nor_marks_the_row(monkeypatch):
    _hook(monkeypatch, "turn", {"session_key": KEY, "run": "r2", "at": 102.0})

    _hook(monkeypatch, "turn-end", {"session_key": KEY, "run": "r1", "at": 101.0, "said": "Done"})

    assert (_row_now().turn_at, _row_now().status) == (102.0, "read")
