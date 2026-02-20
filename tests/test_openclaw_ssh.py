"""Tests for openclaw.ssh — remote session discovery via SSH.

All tests mock subprocess.run to avoid real SSH calls.
"""

import json
import shlex
import subprocess
from unittest.mock import patch

from lemonaid.openclaw.ssh import (
    _ssh_run,
    find_most_recent_session,
    get_last_user_message,
    get_session_key,
    get_session_name,
    list_recent_sessions,
    read_session_header,
)


def _mock_run(stdout: str = "", returncode: int = 0, stderr: str = ""):
    """Create a mock subprocess.CompletedProcess."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# --- _ssh_run ---


@patch("lemonaid.openclaw.ssh.subprocess.run")
def test_ssh_run_success(mock_run):
    mock_run.return_value = _mock_run(stdout="hello\n")
    result = _ssh_run("host", "echo hello")
    assert result == "hello"
    # Verify BatchMode=yes is passed
    call_args = mock_run.call_args[0][0]
    assert "-o" in call_args
    assert "BatchMode=yes" in call_args


@patch("lemonaid.openclaw.ssh.subprocess.run")
def test_ssh_run_failure(mock_run):
    mock_run.return_value = _mock_run(returncode=1, stderr="error")
    assert _ssh_run("host", "bad cmd") is None


@patch("lemonaid.openclaw.ssh.subprocess.run")
def test_ssh_run_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=10)
    assert _ssh_run("host", "slow cmd") is None


@patch("lemonaid.openclaw.ssh.subprocess.run")
def test_ssh_run_os_error(mock_run):
    mock_run.side_effect = OSError("no such file")
    assert _ssh_run("host", "cmd") is None


# --- read_session_header ---


@patch("lemonaid.openclaw.ssh.subprocess.run")
def test_read_session_header_valid(mock_run):
    header = {"type": "session", "id": "abc-123", "cwd": "/home/user"}
    mock_run.return_value = _mock_run(stdout=json.dumps(header))
    result = read_session_header("host", "/path/to/session.jsonl")
    assert result == header


@patch("lemonaid.openclaw.ssh.subprocess.run")
def test_read_session_header_wrong_type(mock_run):
    mock_run.return_value = _mock_run(stdout=json.dumps({"type": "message"}))
    assert read_session_header("host", "/path") is None


@patch("lemonaid.openclaw.ssh.subprocess.run")
def test_read_session_header_invalid_json(mock_run):
    mock_run.return_value = _mock_run(stdout="not json")
    assert read_session_header("host", "/path") is None


@patch("lemonaid.openclaw.ssh.subprocess.run")
def test_read_session_header_ssh_failure(mock_run):
    mock_run.return_value = _mock_run(returncode=1)
    assert read_session_header("host", "/path") is None


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_read_session_header_shell_escapes_path(mock_ssh):
    mock_ssh.return_value = None
    path = "/tmp/it's bad; echo pwned.jsonl"
    read_session_header("host", path)
    assert mock_ssh.call_args[0][1] == f"head -n 1 -- {shlex.quote(path)}"


# --- find_most_recent_session ---


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_find_most_recent_session_success(mock_ssh):
    session_path = (
        "/home/user/.openclaw/agents/agent-1/sessions/a1b2c3d4-e5f6-7890-abcd-ef1234567890.jsonl"
    )
    header = {
        "type": "session",
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "cwd": "/home/user/project",
    }

    mock_ssh.side_effect = [
        session_path,  # ls -t call
        json.dumps(header),  # head -1 call
    ]

    path, session_id, agent_id, cwd = find_most_recent_session("host")
    assert path == session_path
    assert session_id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    assert agent_id == "agent-1"
    assert cwd == "/home/user/project"


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_find_most_recent_session_no_files(mock_ssh):
    mock_ssh.return_value = None
    path, session_id, _agent_id, _cwd = find_most_recent_session("host")
    assert path is None
    assert session_id is None


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_find_most_recent_session_no_uuid(mock_ssh):
    """Non-UUID filename should return all Nones."""
    mock_ssh.side_effect = [
        "/home/.openclaw/agents/a1/sessions/no-uuid-here.jsonl",  # ls
    ]
    path, _session_id, _agent_id, _cwd = find_most_recent_session("host")
    assert path is None


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_find_most_recent_session_extracts_agent_id(mock_ssh):
    """Agent ID comes from the path structure."""
    path_str = (
        "/home/.openclaw/agents/my-fancy-agent/sessions/a1b2c3d4-e5f6-7890-abcd-ef1234567890.jsonl"
    )
    header = {"type": "session", "cwd": "/tmp"}
    mock_ssh.side_effect = [path_str, json.dumps(header)]

    _, _, agent_id, _ = find_most_recent_session("host")
    assert agent_id == "my-fancy-agent"


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_list_recent_sessions_returns_multiple(mock_ssh):
    path_1 = "/home/.openclaw/agents/a1/sessions/a1b2c3d4-e5f6-7890-abcd-ef1234567890.jsonl"
    path_2 = "/home/.openclaw/agents/a2/sessions/b1b2c3d4-e5f6-7890-abcd-ef1234567890.jsonl"
    mock_ssh.side_effect = [
        f"{path_1}\n{path_2}",
        json.dumps({"type": "session", "cwd": "/tmp/one"}),
        json.dumps({"type": "session", "cwd": "/tmp/two"}),
    ]
    sessions = list_recent_sessions("host", limit=2)
    assert len(sessions) == 2
    assert sessions[0][1] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    assert sessions[1][1] == "b1b2c3d4-e5f6-7890-abcd-ef1234567890"


# --- get_session_name ---


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_session_name_label(mock_ssh):
    """Label takes priority over session key."""
    index = {
        "agent:main:testing": {
            "sessionId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "label": "My Cool Session",
        }
    }
    mock_ssh.return_value = json.dumps(index)
    name = get_session_name("host", "agent-1", "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    assert name == "My Cool Session"


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_session_name_key_segment(mock_ssh):
    """Without label, uses last segment of session key."""
    index = {
        "agent:main:testing": {
            "sessionId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        }
    }
    mock_ssh.return_value = json.dumps(index)
    name = get_session_name("host", "agent-1", "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    assert name == "testing"


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_session_name_prefix_match(mock_ssh):
    """Matches by 8-char prefix of session ID."""
    index = {
        "agent:main:testing": {
            "sessionId": "a1b2c3d4",
        }
    }
    mock_ssh.return_value = json.dumps(index)
    name = get_session_name("host", "agent-1", "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    assert name == "testing"


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_session_name_not_found(mock_ssh):
    index = {"agent:main:other": {"sessionId": "ffffffff"}}
    mock_ssh.return_value = json.dumps(index)
    assert get_session_name("host", "agent-1", "a1b2c3d4-xxxx") is None


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_session_name_ssh_failure(mock_ssh):
    mock_ssh.return_value = None
    assert get_session_name("host", "agent-1", "abc") is None


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_session_name_invalid_json(mock_ssh):
    mock_ssh.return_value = "not json"
    assert get_session_name("host", "agent-1", "abc") is None


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_session_name_shell_escapes_agent_id(mock_ssh):
    mock_ssh.return_value = None
    agent_id = "agent'bad;whoami"
    get_session_name("host", agent_id, "abc")
    expected = f"cat -- ~/.openclaw/agents/{shlex.quote(agent_id)}/sessions/sessions.json"
    assert mock_ssh.call_args[0][1] == expected


# --- get_session_key ---


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_session_key_found(mock_ssh):
    index = {
        "agent:main:testing": {
            "sessionId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        }
    }
    mock_ssh.return_value = json.dumps(index)
    key = get_session_key("host", "agent-1", "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    assert key == "agent:main:testing"


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_session_key_not_found(mock_ssh):
    index = {"agent:main:other": {"sessionId": "ffffffff"}}
    mock_ssh.return_value = json.dumps(index)
    assert get_session_key("host", "agent-1", "a1b2c3d4") is None


# --- get_last_user_message ---


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_last_user_message_found(mock_ssh):
    lines = [
        json.dumps(
            {
                "type": "message",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "Done"}]},
            }
        ),
        json.dumps(
            {
                "type": "message",
                "message": {"role": "user", "content": [{"type": "text", "text": "Fix the bug"}]},
            }
        ),
    ]
    mock_ssh.return_value = "\n".join(lines)
    assert get_last_user_message("host", "/path") == "Fix the bug"


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_last_user_message_truncated(mock_ssh):
    long_text = "A" * 200
    lines = [
        json.dumps(
            {
                "type": "message",
                "message": {"role": "user", "content": [{"type": "text", "text": long_text}]},
            }
        ),
    ]
    mock_ssh.return_value = "\n".join(lines)
    result = get_last_user_message("host", "/path")
    assert len(result) == 80
    assert result.endswith("...")


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_last_user_message_no_user_messages(mock_ssh):
    lines = [
        json.dumps({"type": "message", "message": {"role": "assistant", "content": "hello"}}),
    ]
    mock_ssh.return_value = "\n".join(lines)
    assert get_last_user_message("host", "/path") is None


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_last_user_message_ssh_failure(mock_ssh):
    mock_ssh.return_value = None
    assert get_last_user_message("host", "/path") is None


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_last_user_message_string_content(mock_ssh):
    """User message with string content (not list)."""
    lines = [
        json.dumps({"type": "message", "role": "user", "content": "Just a string"}),
    ]
    mock_ssh.return_value = "\n".join(lines)
    assert get_last_user_message("host", "/path") == "Just a string"


@patch("lemonaid.openclaw.ssh._ssh_run")
def test_get_last_user_message_shell_escapes_path(mock_ssh):
    mock_ssh.return_value = None
    path = "/tmp/one'two;echo hi.jsonl"
    get_last_user_message("host", path)
    assert mock_ssh.call_args[0][1] == f"tail -c 65536 -- {shlex.quote(path)}"
