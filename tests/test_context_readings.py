"""What each harness's transcript, and Claude's statusLine, say about context use."""

from pathlib import Path

from lemonaid.claude import context_window
from lemonaid.claude import watcher as claude_watcher
from lemonaid.lemon_watchers.common import ContextReading


def _claude_assistant(input_tokens: int, cache_read: int, sidechain: bool = False) -> dict:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {
            "model": "claude-opus-5-5",
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": 100,
                "cache_read_input_tokens": cache_read,
                "output_tokens": 999,
            },
        },
    }


def test_claude_reads_the_newest_main_thread_request_against_the_statusline_window():
    session = Path("/transcripts/abc-123.jsonl")
    entries = [  # newest first, as the watcher passes them
        {"type": "user"},
        _claude_assistant(5, 70_000, sidechain=True),
        _claude_assistant(2, 40_000),
        _claude_assistant(2, 10_000),
    ]

    assert claude_watcher.get_context(entries, session) == ContextReading(40_102, 0)

    context_window.save(
        {"session_id": "abc-123", "context_window": {"context_window_size": 200_000}}
    )

    assert claude_watcher.get_context(entries, session) == ContextReading(40_102, 200_000)
    assert claude_watcher.get_context([{"type": "user"}], session) is None


def test_the_statusline_saves_a_window_only_when_given_one():
    context_window.save({"session_id": "abc", "context_window": {}})
    context_window.save({"context_window": {"context_window_size": 200_000}})

    assert context_window.read("abc") == 0

    context_window.save({"session_id": "abc", "context_window": {"context_window_size": 1_000}})
    context_window.save({"session_id": "abc", "context_window": {"context_window_size": 2_000}})

    assert context_window.read("abc") == 2_000
