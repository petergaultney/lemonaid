"""A Codex lemon's turns and activity come from Codex's hooks."""

import itertools
import json
import time

import pytest

import lemonaid.inbox.turns
from lemonaid.codex import notify, queued, turns
from lemonaid.inbox import db
from tests import codex_fakes

_THREAD = "01a1f6f1-aed3-7cf2-b97d-b553250d5e44"
_CHANNEL = f"codex:{_THREAD}"


@pytest.fixture
def row():
    with db.connect() as conn:
        return db.add(conn, _CHANNEL, "Waiting", metadata={"session_id": _THREAD}, status="unread")


def _hook(event: str, **fields) -> None:
    notify.handle_turn_hook(
        json.dumps({"hook_event_name": event, "session_id": _THREAD, "model": "gpt-6", **fields})
    )


def _row() -> db.Notification:
    with db.connect() as conn:
        found = db.get_by_channel(conn, _CHANNEL, unread_only=False)
    assert found is not None
    return found


def test_a_prompt_starts_a_turn_and_reads_the_row(row):
    _hook("UserPromptSubmit", prompt="go", turn_id="t1")

    after = _row()
    assert after.turn_at is not None
    assert after.status == "read"
    assert after.message == "Working..."
    assert after.metadata["model"] == "gpt-6"


@pytest.mark.parametrize(
    ("tool_name", "tool_input", "said"),
    [
        ("Bash", {"command": "uv run pytest -q"}, "Running: uv run pytest -q"),
        ("Bash", {"command": ["bash", "-lc", "ls"]}, "Running: ls"),
        (
            "apply_patch",
            {"command": "*** Begin Patch\n*** Update File: src/a.py\n*** Add File: b.md\n"},
            "Editing src/a.py, b.md",
        ),
        ("mcp__github__create_issue", {}, "Using create_issue"),
        ("web_search", {}, "Using web_search"),
    ],
)
def test_a_tool_says_what_the_lemon_is_doing(row, tool_name, tool_input, said):
    _hook("PreToolUse", tool_name=tool_name, tool_input=tool_input, turn_id="t1")

    assert _row().message == said
    assert _row().turn_at is not None


def test_a_long_command_is_cut_short():
    assert turns.describe("Bash", {"command": "x" * 300}) == f"Running: {'x' * 117}..."


def test_an_interrupt_ends_the_turn_as_interrupted(row):
    _hook("UserPromptSubmit", turn_id="t1")
    _hook("Interrupt", turn_id="t1")

    end = turns.last_end(_row())
    assert end is not None and end.interrupted


def test_a_finished_turn_ends_it_normally(row, codex_records):
    codex_records[_THREAD] = codex_fakes.thread(_THREAD)
    _hook("UserPromptSubmit", turn_id="t1")
    assert turns.last_end(_row()) is None

    notify.handle_notification(json.dumps({"type": "agent-turn-complete", "thread-id": _THREAD}))

    end = turns.last_end(_row())
    assert end is not None and not end.interrupted
    assert _row().turn_at is None


def test_a_model_request_records_the_context_used(row):
    _hook("PostModelRequest", status="completed", token_usage={"input_tokens": 41_000})

    assert _row().metadata["context_tokens"] == 41_000


def test_a_hook_for_a_lemon_without_a_row_records_nothing():
    _hook("UserPromptSubmit", turn_id="t1")

    with db.connect() as conn:
        assert db.get_by_channel(conn, _CHANNEL, unread_only=False) is None


def test_an_idle_interrupted_thread_holds_its_queue():
    end = queued.TurnEnd(900.0, True)

    assert "interrupt (Esc)" in queued.unrun(queued.Held(1, 1000.0), end, 1100.0)


def test_a_late_prompt_for_a_finished_turn_does_not_reopen_it(row, codex_records):
    codex_records[_THREAD] = codex_fakes.thread(_THREAD)
    notify.handle_notification(
        json.dumps({"type": "agent-turn-complete", "thread-id": _THREAD, "turn-id": "t1"})
    )
    finished = _row()

    _hook("UserPromptSubmit", turn_id="t1")
    _hook("PreToolUse", turn_id="t1", tool_name="Bash", tool_input={"command": "ls"})

    after = _row()
    assert after.turn_at is None
    assert after.status == finished.status == "unread"
    assert after.message == finished.message


def test_a_late_interrupt_does_not_end_the_next_turn(row):
    _hook("UserPromptSubmit", turn_id="01a1f6f1-0000-7000-8000-000000000001")
    _hook("UserPromptSubmit", turn_id="01a1f6f1-0000-7000-8000-000000000002")

    _hook("Interrupt", turn_id="01a1f6f1-0000-7000-8000-000000000001")

    assert _row().turn_at is not None
    assert turns.last_end(_row()) is None


def test_late_events_from_a_superseded_turn_leave_the_current_one_running(row):
    t1, t2 = "01a1f6f1-0000-7000-8000-000000000001", "01a1f6f1-0000-7000-8000-000000000002"
    _hook("UserPromptSubmit", turn_id=t1)
    _hook("UserPromptSubmit", turn_id=t2)

    _hook("PreToolUse", turn_id=t1, tool_name="Bash", tool_input={"command": "ls"})
    _hook("Interrupt", turn_id=t1)

    after = _row()
    assert after.turn_at is not None
    assert after.metadata["turn_id"] == t2
    assert after.message == "Working..."


@pytest.mark.parametrize("ending", ["interrupt", "complete"])
def test_an_end_that_arrives_before_its_start_still_ends_the_turn(row, codex_records, ending):
    codex_records[_THREAD] = codex_fakes.thread(_THREAD)
    t1 = "01a1f6f1-0000-7000-8000-000000000001"
    if ending == "interrupt":
        _hook("Interrupt", turn_id=t1)
    else:
        notify.handle_notification(
            json.dumps({"type": "agent-turn-complete", "thread-id": _THREAD, "turn-id": t1})
        )

    _hook("UserPromptSubmit", turn_id=t1)

    end = turns.last_end(_row())
    assert _row().turn_at is None
    assert end is not None and end.interrupted is (ending == "interrupt")


def test_a_late_end_of_an_older_turn_leaves_the_newer_one_running(row, codex_records):
    codex_records[_THREAD] = codex_fakes.thread(_THREAD)
    t1, t2 = "01a1f6f1-0000-7000-8000-000000000001", "01a1f6f1-0000-7000-8000-000000000002"
    _hook("UserPromptSubmit", turn_id=t1)
    _hook("UserPromptSubmit", turn_id=t2)

    notify.handle_notification(
        json.dumps({"type": "agent-turn-complete", "thread-id": _THREAD, "turn-id": t1})
    )

    assert _row().turn_at is not None
    assert _row().metadata["turn_id"] == t2


_T1, _T2 = "01a1f6f1-0000-7000-8000-000000000001", "01a1f6f1-0000-7000-8000-000000000002"
_EVENTS = {"start t1": _T1, "end t1": _T1, "start t2": _T2, "end t2": _T2}


def _orders():
    """Every order of every non-empty subset of two turns' starts and ends."""
    for size in range(1, len(_EVENTS) + 1):
        for chosen in itertools.combinations(_EVENTS, size):
            yield from itertools.permutations(chosen)


@pytest.mark.parametrize("ending", ["Interrupt", "turn complete"])
@pytest.mark.parametrize("order", list(_orders()), ids=" -> ".join)
def test_whatever_order_hooks_arrive_in_the_latest_turn_decides(row, codex_records, order, ending):
    """Codex runs these hooks, and its notify program, concurrently, so any order can arrive.
    The lemon is mid-turn exactly when its latest started turn is later than its latest
    ended one."""
    codex_records[_THREAD] = codex_fakes.thread(_THREAD)
    for name in order:
        turn = _EVENTS[name]
        if name.startswith("start"):
            _hook("UserPromptSubmit", turn_id=turn)
        elif ending == "Interrupt":
            _hook("Interrupt", turn_id=turn)
        else:
            notify.handle_notification(
                json.dumps({"type": "agent-turn-complete", "thread-id": _THREAD, "turn-id": turn})
            )

    started = max((_EVENTS[n] for n in order if n.startswith("start")), default="")
    ended = max((_EVENTS[n] for n in order if n.startswith("end")), default="")
    after = _row()
    assert lemonaid.inbox.turns.mid_turn(after, time.time()) is (started > ended)
    assert after.metadata.get("turn_ended_id", "") == ended
