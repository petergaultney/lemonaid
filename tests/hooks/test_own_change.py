"""The own-change hook: any tool call's change to a watched doc, and any push, is the lemon's own."""

import io
import json

import pytest

from lemonaid.hooks import own_change
from lemonaid.watch import doc_events, own_edits, own_pushes

_SESSION = "11111111-2222-3333-4444-555555555555"
_QUIET = "git" + " push -q"  # split, so a session running the hook can edit this file
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
        lambda: doc.write_text(doc.read_text() + "Sam's, mid test run.\n"),
        {"command": "uv run pytest"},
    )

    assert len(_poll_twice(w)) == 1


def test_a_change_between_tool_calls_still_wakes(tmp_path, doc):
    w = _watch(tmp_path, doc, "claude")
    doc.write_text(doc.read_text() + "Sam's.\n")
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
    doc.write_text(doc.read_text() + "Sam's.\n")
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
    ask = '{{authorId="1" author="Sam">>is this   right?<<}}'
    doc.write_text(doc.read_text() + f"\n{ask}\n")
    w = _watch(tmp_path, doc, "claude")
    assert len(_poll_twice(w)) == 1

    doc.write_text(doc.read_text().replace("is this   right?", "is this right?"))

    assert _poll_twice(w) == []


@pytest.mark.parametrize("harness", ["claude", "codex"])
@pytest.mark.parametrize("source", ["Docs", "Watching"])
def test_a_doc_in_the_attached_brief_is_recorded_between_waits(
    tmp_path, doc, harness, monkeypatch, source
):
    _watch(tmp_path, doc, harness)
    own_edits.unregister(tmp_path, f"{harness}-{_SESSION}", doc)
    brief = tmp_path / "brief.md"
    brief.write_text(
        f"# task\n\nBrief-ID: task.IndexElf\n\n## Now\n\n### Docs\n\n| Document | Purpose | Watch |\n|---|---|---|\n| `{doc}` | Review | All edits |\n"
    )
    if source == "Watching":
        brief.write_text(
            f"# task\n\nBrief-ID: task.IndexElf\n\n## Watching\n- `lemonaid watch doc --wait {doc}`\n"
        )
    monkeypatch.setattr(own_change.waiter_check, "attached_brief", lambda *args: brief)
    _tool_call(
        tmp_path,
        harness,
        lambda: doc.write_text(doc.read_text() + "Mine between waits.\n"),
        {"file_path": str(doc)},
    )
    rearmed = _watch(tmp_path, doc, harness)
    assert _poll_twice(rearmed) == []
    doc.write_text(doc.read_text() + "Someone else's.\n")
    assert len(_poll_twice(rearmed)) == 1


@pytest.mark.parametrize(
    ("command", "hidden"),
    [
        ("git push origin b", False),
        ("rg '" + _QUIET + "' docs", False),
        ("echo 'unbalanced", False),
        (_QUIET.replace("-q", "origin b &") + ">/dev/null", True),
        ("git push --force-with-lease origin b 2>&1 | grep -- '->'", False),
        ("git push origin b && rm -q x", False),
        ("git push origin b; ls 2>/dev/null", False),
        ("git push -q origin b", True),
        ("git -C /x push -qu origin b", True),
        ("git push origin --quiet", True),
        ("git push origin b 2>/dev/null", True),
        ("git push origin b >/dev/null 2>&1", True),
    ],
)
def test_a_push_hides_its_heads_when_quiet_or_stderr_is_discarded(command, hidden):
    assert own_pushes.hides_heads(command) is hidden


def test_a_quiet_codex_push_is_refused_before_it_runs(monkeypatch, capsys, tmp_path):
    event = {"session_id": _SESSION, "tool_input": {"command": "git push -q origin b"}}
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({**event, "hook_event_name": "PreToolUse"}))
    )

    with pytest.raises(SystemExit) as stopped:
        own_change.handle("codex")

    assert stopped.value.code == 2
    assert "without -q" in capsys.readouterr().err
    assert own_change.refusal({**event, "hook_event_name": "PostToolUse"}) == ""


@pytest.mark.parametrize(
    "tool_input",
    [
        {"file_path": "/x/notes.md", "old_string": "a", "new_string": f"Never run {_QUIET}"},
        {"patch": f"*** Update File: notes.md\n+{_QUIET} origin b\n"},
        {"command": f"rg '{_QUIET}' docs"},
        {
            "file_path": "/x/notes.md",
            "old_string": "a",
            "new_string": f'Codex runs tools.exec_command({{cmd: "{_QUIET} origin b"}})',
        },
    ],
)
def test_text_that_only_mentions_a_quiet_push_is_not_refused(tool_input):
    event = {"session_id": _SESSION, "hook_event_name": "PreToolUse", "tool_input": tool_input}

    assert own_change.refusal(event) == ""


@pytest.mark.parametrize(
    "tool_input",
    [
        {"command": f"{_QUIET} origin b"},
        {"cmd": f"{_QUIET} origin b"},
        {"input": f'const r = await tools.exec_command({{"cmd":"{_QUIET} origin b"}});'},
        f'tools.exec_command({{"cmd":"cd /x && {_QUIET} origin b"}})',
        f'tools.exec_command({{cmd: "{_QUIET} origin b"}})',
        f'tools.exec_command({{"workdir":"/tmp","cmd":"{_QUIET} origin b"}})',
        f"tools.exec_command({{ workdir: '/tmp', cmd: '{_QUIET} origin b' }})",
        f"await tools.exec_command({{\n  cmd: `{_QUIET} origin b`,\n}})",
    ],
)
def test_a_quiet_push_is_refused_in_every_harness_payload(tool_input):
    event = {"session_id": _SESSION, "hook_event_name": "PreToolUse", "tool_input": tool_input}

    assert "without -q" in own_change.refusal(event)


@pytest.mark.parametrize(("mode", "decision"), [("bypassPermissions", "allow"), ("default", "ask")])
def test_a_quiet_claude_push_runs_with_its_heads_printed(monkeypatch, capsys, mode, decision):
    tool_input = {"command": f"{_QUIET}u origin b && echo done", "description": "Push"}
    event = {
        "session_id": _SESSION,
        "hook_event_name": "PreToolUse",
        "permission_mode": mode,
        "tool_input": tool_input,
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    own_change.handle("claude")

    output = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert output["permissionDecision"] == decision
    assert output["updatedInput"] == {
        "command": "git push -u origin b && echo done",
        "description": "Push",
    }
    assert "Don't push quietly" in output["additionalContext"]


def test_a_claude_push_with_stderr_discarded_is_still_refused():
    command = _QUIET.replace(" -q", "") + " origin b 2>/dev" + "/null"
    event = {
        "session_id": _SESSION,
        "hook_event_name": "PreToolUse",
        "tool_input": {"command": command},
    }

    assert own_change.rewrite(event, "claude") is None
    assert own_change.refusal(event)


@pytest.mark.parametrize(
    ("command", "rewritten"),
    [
        (_QUIET + ' "/tmp/remote  repo.git" HEAD', 'git push "/tmp/remote  repo.git" HEAD'),
        (_QUIET + " origin HEAD --push-option='note -q text'", None),
        (_QUIET + "u origin b; ls -q", "git push -u origin b; ls -q"),
    ],
)
def test_a_rewrite_changes_nothing_but_the_quiet_flag_or_is_not_made(command, rewritten):
    assert own_pushes.loud(command) == rewritten
