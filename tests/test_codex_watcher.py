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
            "arguments": "{\"command\":\"rg -n test\"}",
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
