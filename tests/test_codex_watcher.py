"""Tests for lemonaid.codex.watcher module."""

from lemonaid.codex import watcher


def test_describe_activity_local_shell_call():
    entry = {"type": "local_shell_call", "action": {"command": ["bash", "-lc", "pytest"]}}
    assert watcher.describe_activity(entry) == "Running: pytest"


def test_describe_activity_response_item_function_call_shell_command():
    entry = {
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "shell_command",
            "arguments": '{"command":"rg -n test"}',
        },
    }
    assert watcher.describe_activity(entry) == "Running: rg -n test"


def test_describe_activity_response_item_web_search_call():
    entry = {
        "type": "response_item",
        "payload": {"type": "web_search_call", "action": {"query": "lemonaid docs"}},
    }
    assert watcher.describe_activity(entry) == "Searching: lemonaid docs"


def test_should_dismiss_for_response_item_message():
    entry = {"type": "response_item", "payload": {"type": "message", "role": "assistant"}}
    assert watcher.should_dismiss(entry) is True


def test_describe_activity_custom_tool_call_exec():
    """`exec` is how Codex runs nearly everything, and it carries no command field."""
    entry = {
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call",
            "name": "exec",
            "input": 'const r = await tools.exec_command({"cmd":"rg -n needle"});',
        },
    }
    assert watcher.describe_activity(entry) == "Running: rg -n needle"


def test_describe_activity_custom_tool_call_unescapes_the_command():
    entry = {
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call",
            "name": "exec",
            "input": 'tools.exec_command({"cmd":"echo \\"hi\\"\\npwd"})',
        },
    }
    assert watcher.describe_activity(entry) == 'Running: echo "hi"\npwd'


def test_describe_activity_custom_tool_call_patch_names_the_file():
    entry = {
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call",
            "name": "exec",
            "input": 'const patch = "*** Begin Patch\\n*** Update File: /a/b/thing.py\\n@@\\n-x\\n+y";',
        },
    }
    assert watcher.describe_activity(entry) == "Editing thing.py"


def test_describe_activity_custom_tool_call_unparseable_still_describes():
    """A description that carries a fresh timestamp is what unsticks the row."""
    entry = {
        "type": "response_item",
        "payload": {"type": "custom_tool_call", "name": "exec", "input": "something novel"},
    }
    assert watcher.describe_activity(entry) == "Running command"


def test_describe_activity_task_started():
    """The first entry after you reply - without it the row shows the previous turn."""
    entry = {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "x"}}
    assert watcher.describe_activity(entry) == "Working..."


def test_describe_activity_agent_message():
    entry = {
        "type": "event_msg",
        "payload": {"type": "agent_message", "message": "Found it.\nMore detail here."},
    }
    assert watcher.describe_activity(entry) == "Found it."


def test_describe_activity_patch_apply_end():
    entry = {"type": "event_msg", "payload": {"type": "patch_apply_end", "success": True}}
    assert watcher.describe_activity(entry) == "Applied changes"


def test_describe_activity_mcp_tool_call_end():
    entry = {
        "type": "event_msg",
        "payload": {
            "type": "mcp_tool_call_end",
            "invocation": {"server": "codex_apps", "tool": "github.create_pull_request"},
        },
    }
    assert watcher.describe_activity(entry) == "Using github.create_pull_request"


def test_describe_activity_ignores_uninteresting_events():
    """token_count arrives constantly and says nothing about what is happening."""
    assert (
        watcher.describe_activity({"type": "event_msg", "payload": {"type": "token_count"}}) is None
    )


def test_should_dismiss_custom_tool_call():
    entry = {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec"}}
    assert watcher.should_dismiss(entry) is True


def test_should_dismiss_task_started():
    assert (
        watcher.should_dismiss({"type": "event_msg", "payload": {"type": "task_started"}}) is True
    )


def test_should_not_dismiss_token_count():
    assert (
        watcher.should_dismiss({"type": "event_msg", "payload": {"type": "token_count"}}) is False
    )
