"""Tests for lemonaid.claude.notify module."""

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

from lemonaid.claude import notify


@contextmanager
def _fake_connect():
    yield object()


def test_handle_submit_registers_working():
    payload = '{"session_id":"abc123","cwd":"/tmp/project","hook_event_name":"UserPromptSubmit"}'

    with (
        patch("lemonaid.claude.notify.db.connect", _fake_connect),
        patch(
            "lemonaid.claude.notify.resolve_session_name",
            return_value=notify.SessionName("Test Session", notify.TITLE_SOURCE),
        ),
        patch("lemonaid.claude.notify.get_tmux_session_name", return_value=None),
        patch("lemonaid.claude.notify.get_tty", return_value="/dev/ttys001"),
        patch("lemonaid.claude.notify.detect_terminal_switch_source", return_value="tmux"),
        patch("lemonaid.claude.notify.get_git_branch", return_value="main"),
        patch("lemonaid.claude.notify.db.register_working") as mock_register,
    ):
        notify.handle_submit(stdin_data=payload)

    kwargs = mock_register.call_args.kwargs
    assert kwargs["channel"] == "claude:abc123"
    assert kwargs["name"] == "Test Session"
    assert kwargs["message"] == "Working in tmp/project"
    assert kwargs["metadata"]["session_id"] == "abc123"
    assert kwargs["metadata"]["tty"] == "/dev/ttys001"
    assert kwargs["switch_source"] == "tmux"


def test_handle_submit_headless_has_no_switch_source():
    payload = '{"session_id":"abc123","cwd":"/tmp/project"}'

    with (
        patch("lemonaid.claude.notify.db.connect", _fake_connect),
        patch("lemonaid.claude.notify.resolve_session_name", return_value=None),
        patch("lemonaid.claude.notify.get_tmux_session_name", return_value=None),
        patch("lemonaid.claude.notify.get_name_from_cwd", return_value="project"),
        patch("lemonaid.claude.notify.get_tty", return_value=None),
        patch("lemonaid.claude.notify.detect_terminal_switch_source", return_value="unknown"),
        patch("lemonaid.claude.notify.get_git_branch", return_value=None),
        patch("lemonaid.claude.notify.db.register_working") as mock_register,
    ):
        notify.handle_submit(stdin_data=payload)

    assert mock_register.call_args.kwargs["switch_source"] is None


def _submit_with(tmux_session, tmux_window, register):
    """Run the submit hook with the tmux environment stubbed out."""
    return (
        patch("lemonaid.claude.notify.db.connect", _fake_connect),
        patch("lemonaid.claude.notify.resolve_session_name", return_value=None),
        patch("lemonaid.claude.notify.get_tmux_session_name", return_value=tmux_session),
        patch("lemonaid.claude.notify.get_tmux_window_index", return_value=tmux_window),
        patch("lemonaid.claude.notify.get_name_from_cwd", return_value="project"),
        patch("lemonaid.claude.notify.get_tty", return_value=None),
        patch("lemonaid.claude.notify.detect_terminal_switch_source", return_value="tmux"),
        patch("lemonaid.claude.notify.get_git_branch", return_value=None),
        patch("lemonaid.claude.notify.db.register_working", register),
    )


def test_submit_records_where_the_session_is_running():
    """Without this the inbox survives a tmux crash but can't rebuild the layout."""
    payload = '{"session_id":"abc123","cwd":"/tmp/project"}'
    register = MagicMock()

    with ExitStack() as stack:
        for ctx in _submit_with("relay", "4", register):
            stack.enter_context(ctx)
        notify.handle_submit(stdin_data=payload)

    metadata = register.call_args.kwargs["metadata"]
    assert metadata["tmux_session"] == "relay"
    assert metadata["tmux_window"] == "4"


def test_submit_records_no_location_outside_tmux():
    payload = '{"session_id":"abc123","cwd":"/tmp/project"}'
    register = MagicMock()

    with ExitStack() as stack:
        for ctx in _submit_with(None, None, register):
            stack.enter_context(ctx)
        notify.handle_submit(stdin_data=payload)

    metadata = register.call_args.kwargs["metadata"]
    assert "tmux_session" not in metadata
    assert "tmux_window" not in metadata


def _message_for(payload: str) -> str:
    """The inbox message a hook payload produces."""
    with (
        patch("lemonaid.claude.notify.db.connect", _fake_connect),
        patch(
            "lemonaid.claude.notify.resolve_session_name",
            return_value=notify.SessionName("Test Session", notify.TITLE_SOURCE),
        ),
        patch("lemonaid.claude.notify.get_tmux_session_name", return_value=None),
        patch("lemonaid.claude.notify.get_tty", return_value="/dev/ttys001"),
        patch("lemonaid.claude.notify.detect_terminal_switch_source", return_value="tmux"),
        patch("lemonaid.claude.notify.get_git_branch", return_value="main"),
        patch("lemonaid.claude.notify.db.get_by_channel", return_value=None),
        patch("lemonaid.claude.notify.db.add") as mock_add,
    ):
        notify.handle_notification(stdin_data=payload)

    return mock_add.call_args.kwargs["message"]


def test_a_finished_turn_says_it_is_waiting():
    """Stop carries no notification_type, and used to report its hook's name."""
    message = _message_for('{"session_id":"abc123","cwd":"/tmp/project","hook_event_name":"Stop"}')
    assert message == "Waiting in tmp/project"
    assert "Stop" not in message


def test_a_permission_prompt_still_says_permission():
    assert (
        _message_for(
            '{"session_id":"abc123","cwd":"/tmp/project",'
            '"hook_event_name":"Notification","notification_type":"permission_prompt"}'
        )
        == "Permission needed in tmp/project"
    )
