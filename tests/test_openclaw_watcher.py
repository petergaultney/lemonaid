"""Tests for openclaw.watcher — activity detection, dismiss, and attention logic."""

from lemonaid.openclaw.watcher import (
    describe_activity,
    needs_attention,
    should_dismiss,
)

# --- describe_activity ---


def test_describe_tool_use_read():
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/src/main.py"}}
            ],
        },
    }
    assert describe_activity(entry) == "Reading main.py"


def test_describe_tool_use_edit():
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/a/b/config.js"}}
            ],
        },
    }
    assert describe_activity(entry) == "Editing config.js"


def test_describe_tool_use_write():
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "Write", "input": {"file_path": "/new.txt"}}],
        },
    }
    assert describe_activity(entry) == "Writing new.txt"


def test_describe_tool_use_bash():
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "pytest tests/"}}
            ],
        },
    }
    assert describe_activity(entry) == "Running: pytest tests/"


def test_describe_tool_use_bash_long_command():
    long_cmd = "x" * 200
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": long_cmd}}],
        },
    }
    result = describe_activity(entry)
    assert result.endswith("...")
    assert len(result) <= 130


def test_describe_tool_use_grep():
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "Grep", "input": {"pattern": "def main"}}],
        },
    }
    assert describe_activity(entry) == "Searching: def main"


def test_describe_tool_use_glob():
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "Glob", "input": {"pattern": "**/*.py"}}],
        },
    }
    assert describe_activity(entry) == "Finding: **/*.py"


def test_describe_tool_use_web_fetch():
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "WebFetch", "input": {"url": "https://example.com"}}
            ],
        },
    }
    assert describe_activity(entry) == "Fetching: https://example.com"


def test_describe_tool_use_web_search():
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "WebSearch", "input": {"query": "python async"}}
            ],
        },
    }
    assert describe_activity(entry) == "Searching: python async"


def test_describe_tool_use_unknown():
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "CustomTool", "input": {}}],
        },
    }
    assert describe_activity(entry) == "Using CustomTool"


def test_describe_tool_use_toolcall_format():
    """OpenClaw may use 'toolCall' type and 'toolName' field."""
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [{"type": "toolCall", "toolName": "Read", "arguments": {"path": "/a.py"}}],
        },
    }
    assert describe_activity(entry) == "Reading a.py"


def test_describe_text_response():
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Here's the plan:\nStep 1..."}],
        },
    }
    assert describe_activity(entry) == "Here's the plan:"


def test_describe_text_truncation():
    entry = {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "A" * 300}],
        },
    }
    result = describe_activity(entry)
    assert len(result) <= 203
    assert result.endswith("...")


def test_describe_string_content():
    """Content can be a plain string (not a list)."""
    entry = {
        "type": "message",
        "message": {"role": "assistant", "content": "Just some text"},
    }
    assert describe_activity(entry) == "Just some text"


def test_describe_compaction():
    entry = {"type": "compaction"}
    assert describe_activity(entry) == "Compacting context..."


def test_describe_custom_message():
    entry = {
        "type": "custom_message",
        "content": [{"type": "text", "text": "Extension says hello"}],
    }
    assert describe_activity(entry) == "Extension says hello"


def test_describe_user_message_returns_none():
    entry = {
        "type": "message",
        "message": {"role": "user", "content": "Please fix the bug"},
    }
    assert describe_activity(entry) is None


def test_describe_unknown_type():
    assert describe_activity({"type": "custom"}) is None
    assert describe_activity({"type": "branch_summary"}) is None
    assert describe_activity({}) is None


def test_describe_role_at_top_level():
    """Role can appear at top level instead of nested in message."""
    entry = {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Top-level role"}],
    }
    assert describe_activity(entry) == "Top-level role"


# --- should_dismiss ---


def test_dismiss_user_message():
    entry = {
        "type": "message",
        "message": {"role": "user", "content": "Next step please"},
    }
    assert should_dismiss(entry) is True


def test_dismiss_user_role_at_top_level():
    entry = {"type": "message", "role": "user"}
    assert should_dismiss(entry) is True


def test_dismiss_assistant_message():
    entry = {
        "type": "message",
        "message": {"role": "assistant", "content": "Done!"},
    }
    assert should_dismiss(entry) is False


def test_dismiss_non_message():
    assert should_dismiss({"type": "compaction"}) is False
    assert should_dismiss({"type": "custom"}) is False
    assert should_dismiss({}) is False


# --- needs_attention ---


def test_attention_assistant_stop():
    entry = {
        "type": "message",
        "message": {"role": "assistant", "stopReason": "stop"},
    }
    assert needs_attention(entry) is True


def test_attention_stop_reason_at_top_level():
    entry = {
        "type": "message",
        "role": "assistant",
        "stopReason": "stop",
    }
    assert needs_attention(entry) is True


def test_attention_assistant_no_stop_reason():
    entry = {
        "type": "message",
        "message": {"role": "assistant"},
    }
    assert needs_attention(entry) is False


def test_attention_assistant_max_tokens():
    entry = {
        "type": "message",
        "message": {"role": "assistant", "stopReason": "max_tokens"},
    }
    assert needs_attention(entry) is False


def test_attention_user_with_stop_reason():
    """User messages with stopReason should NOT trigger attention."""
    entry = {
        "type": "message",
        "message": {"role": "user", "stopReason": "stop"},
    }
    assert needs_attention(entry) is False


def test_attention_non_message():
    assert needs_attention({"type": "compaction"}) is False
    assert needs_attention({}) is False
