from pathlib import Path

from lemonaid.hooks import tool_calls


def _write(**fields) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": "/n/a.md"}, **fields}


def test_a_claude_write_creates_only_when_its_result_says_so():
    assert tool_calls.created(_write()) == []
    assert tool_calls.created(_write(tool_response={"type": "update"})) == []
    assert tool_calls.created(_write(tool_response={"type": "create"})) == [Path("/n/a.md")]


def test_a_claude_write_of_patch_text_creates_only_its_own_file():
    patch = "*** Begin Patch\n*** Add File: elsewhere.md\n*** End Patch\n"
    data = {"tool_name": "Write", "tool_input": {"file_path": "/n/p.md", "content": patch}}

    assert tool_calls.created(data) == []
