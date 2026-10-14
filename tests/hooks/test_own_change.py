"""The own-change hook: any tool call's change to a watched doc, and any push, is the lemon's own."""

import pytest

from lemonaid.hooks import own_change
from lemonaid.watch import doc_events, own_pushes

_SESSION = "11111111-2222-3333-4444-555555555555"
_PUSH_OUTPUT = (
    "To github.com:o/r.git\n"
    "   1a2b3c4..5d6e7f8  lemonaid/x -> lemonaid/x\n"
    " + 0a0a0a0...9f9f9f9 lemonaid/y -> lemonaid/y (forced update)\n"
)


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "review.md"
    path.write_text("# Review\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    return path


def _watch(state_dir, doc, harness):
    return doc_events.open_watch(
        state_dir / "cursors",
        doc,
        "Author (X)",
        [],
        edits=True,
        quiet=0,
        writer=f"{harness}-{_SESSION}",
        own_root=state_dir,
    )


def _tool_call(state_dir, harness, change, tool_input=None, tool_response=None, call="call_1"):
    event = {"session_id": _SESSION, "tool_use_id": call, "tool_input": tool_input or {}}
    own_change.record({**event, "hook_event_name": "PreToolUse"}, harness, state_dir)
    change()
    own_change.record(
        {**event, "hook_event_name": "PostToolUse", "tool_response": tool_response or {}},
        harness,
        state_dir,
    )


def _poll_twice(w) -> list[str]:
    sent: list[str] = []
    for _ in range(2):
        doc_events.poll(w, lambda message: sent.append(message) or True)
    return sent


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_a_shell_command_editing_a_watched_doc_is_the_lemons_own(tmp_path, doc, harness):
    w = _watch(tmp_path, doc, harness)
    _tool_call(
        tmp_path,
        harness,
        lambda: doc.write_text(doc.read_text() + "Mine.\n"),
        {"command": f"python3 rewrite.py {doc}"},
    )

    assert _poll_twice(w) == []


def test_a_human_edit_during_a_call_that_does_not_name_the_doc_wakes(tmp_path, doc):
    w = _watch(tmp_path, doc, "claude")
    _tool_call(
        tmp_path,
        "claude",
        lambda: doc.write_text(doc.read_text() + "Peter's, mid test run.\n"),
        {"command": "uv run pytest"},
    )

    assert len(_poll_twice(w)) == 1


def test_a_change_between_tool_calls_still_wakes(tmp_path, doc):
    w = _watch(tmp_path, doc, "claude")
    doc.write_text(doc.read_text() + "Peter's.\n")
    _tool_call(tmp_path, "claude", lambda: None, {"command": "ls"})

    assert len(_poll_twice(w)) == 1


def test_parallel_tool_calls_that_see_the_same_change_record_it_once(tmp_path, doc):
    w = _watch(tmp_path, doc, "claude")
    pre = {
        "session_id": _SESSION,
        "hook_event_name": "PreToolUse",
        "tool_input": {"file_path": str(doc)},
    }
    for call in ("call_1", "call_2"):
        own_change.record({**pre, "tool_use_id": call}, "claude", tmp_path)
    doc.write_text(doc.read_text() + "Mine.\n")
    for call in ("call_1", "call_2"):
        own_change.record(
            {**pre, "hook_event_name": "PostToolUse", "tool_use_id": call}, "claude", tmp_path
        )

    assert _poll_twice(w) == []


def test_re_padding_a_table_wakes_nobody(tmp_path, doc):
    w = _watch(tmp_path, doc, "claude")
    doc.write_text("# Review\n\n| a   | b   |\n| --- | --- |\n| 1   | 2   |\n")

    assert _poll_twice(w) == []
    doc.write_text(doc.read_text() + "Peter's.\n")
    assert len(_poll_twice(w)) == 1


def test_a_successful_push_records_its_heads(tmp_path):
    own_pushes.register(tmp_path, f"claude-{_SESSION}")
    _tool_call(
        tmp_path,
        "claude",
        lambda: None,
        {"command": "git push --force-with-lease"},
        {"stdout": "", "stderr": _PUSH_OUTPUT},
    )

    writer = f"claude-{_SESSION}"
    assert own_pushes.is_own(tmp_path, writer, "5d6e7f8" + "0" * 33)
    assert own_pushes.is_own(tmp_path, writer, "9f9f9f9" + "0" * 33)
    assert not own_pushes.is_own(tmp_path, writer, "1a2b3c4" + "0" * 33)


def test_push_output_from_a_command_that_did_not_push_is_ignored(tmp_path):
    own_pushes.register(tmp_path, f"claude-{_SESSION}")
    _tool_call(
        tmp_path, "claude", lambda: None, {"command": "cat log.txt"}, {"stdout": _PUSH_OUTPUT}
    )

    assert not own_pushes.is_own(tmp_path, f"claude-{_SESSION}", "5d6e7f8" + "0" * 33)


@pytest.mark.parametrize(
    ("command", "push"),
    [
        ("git push", True),
        ("git -C ../x push --force-with-lease origin HEAD", True),
        ("git --no-pager push", True),
        ("git fetch origin push-fix", False),
        ("echo git; push", False),
    ],
)
def test_only_a_git_push_subcommand_is_a_push(command, push):
    assert own_pushes.is_push(command) is push


def test_reformatting_a_reported_thread_does_not_report_it_again(tmp_path, doc):
    ask = '{{authorId="1" author="Peter">>is this   right?<<}}'
    doc.write_text(doc.read_text() + f"\n{ask}\n")
    w = _watch(tmp_path, doc, "claude")
    assert len(_poll_twice(w)) == 1

    doc.write_text(doc.read_text().replace("is this   right?", "is this right?"))

    assert _poll_twice(w) == []
