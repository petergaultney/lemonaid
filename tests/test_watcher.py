"""Tests for lemonaid.claude.watcher module."""

from lemonaid.claude.watcher import describe_activity


def test_describe_activity_tool_use_read():
    """describe_activity should describe Read tool use."""
    entry = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/src/main.py"}}
            ]
        },
    }
    assert describe_activity(entry) == "Reading main.py"


def test_describe_activity_tool_use_edit():
    """describe_activity should describe Edit tool use."""
    entry = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/src/config.js"}}
            ]
        },
    }
    assert describe_activity(entry) == "Editing config.js"


def test_describe_activity_tool_use_bash():
    """describe_activity should describe Bash tool use."""
    entry = {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "pytest tests/"}}]
        },
    }
    assert describe_activity(entry) == "Running pytest"


def test_describe_activity_tool_use_grep():
    """describe_activity should describe Grep tool use."""
    entry = {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "Grep", "input": {"pattern": "def main"}}]
        },
    }
    assert describe_activity(entry) == "Searching for def main"


def test_describe_activity_tool_use_task():
    """describe_activity should describe Task tool use."""
    entry = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Task",
                    "input": {"description": "explore codebase"},
                }
            ]
        },
    }
    assert describe_activity(entry) == "Task: explore codebase"


def test_describe_activity_text_response():
    """describe_activity should extract first line of text response."""
    entry = {
        "type": "assistant",
        "message": {
            "content": [{"type": "text", "text": "Here's the solution:\n\nFirst, we need to..."}]
        },
    }
    assert describe_activity(entry) == "Here's the solution:"


def test_describe_activity_text_truncation():
    """describe_activity should truncate very long text."""
    entry = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "A" * 300}]},
    }
    result = describe_activity(entry)
    assert len(result) <= 203  # 200 chars + "..."
    assert result.endswith("...")


def test_describe_activity_user_input():
    """describe_activity returns None for user input (no message to show)."""
    entry = {
        "type": "user",
        "message": {"content": "Please fix the bug"},
    }
    # describe_activity returns None, but should_dismiss returns True
    assert describe_activity(entry) is None

    from lemonaid.claude.watcher import should_dismiss

    assert should_dismiss(entry) is True


def test_describe_activity_user_tool_result():
    """describe_activity should return None for tool results."""
    entry = {
        "type": "user",
        "message": {"content": [{"type": "tool_result"}]},
    }
    assert describe_activity(entry) is None


def test_describe_activity_unknown():
    """describe_activity should return None for unknown types."""
    entry = {"type": "system"}
    assert describe_activity(entry) is None


def test_describe_activity_thinking_only():
    """describe_activity should return None for thinking-only entries."""
    entry = {
        "type": "assistant",
        "message": {"content": [{"type": "thinking", "thinking": "Let me think about this..."}]},
    }
    # Thinking-only entries return None so we keep looking for better messages
    assert describe_activity(entry) is None
