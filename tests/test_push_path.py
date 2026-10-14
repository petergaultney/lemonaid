"""`watch --self --status` says which path this session's batches take."""

import pytest

from lemonaid.claude import inbound, session_socket
from lemonaid.watch import push_path


def _facts(**facts) -> push_path.Facts:
    return push_path.Facts(
        **{"socket": True, "setting": "accepted", "scout": False, "waiter": False, **facts}
    )


def test_a_scout_pushing_into_an_accepting_session_is_quiet():
    found = push_path.path_of(_facts(scout=True))

    assert found.text == "pushed through the session socket" and not found.loud


def test_no_socket_and_no_waiter_is_loud():
    assert push_path.path_of(_facts(socket=False, setting="")).loud


def test_a_background_waiter_is_quiet_without_a_socket_or_when_the_session_would_hold():
    assert not push_path.path_of(_facts(socket=False, setting="", waiter=True)).loud
    assert not push_path.path_of(_facts(setting="not accepted", waiter=True)).loud


def test_a_session_that_would_hold_pushes_is_loud_without_a_waiter():
    assert "crossSessionInbound: unknown" in push_path.path_of(_facts(setting="unknown")).text


def test_status_line_reports_each_fact():
    line = push_path.status_line(_facts(setting="unknown"))

    assert line.startswith("socket found, crossSessionInbound unknown, scout not running")


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], "unknown"),
        (["claude", "--permission-mode", "auto"], "accepted"),
        (["claude", "--dangerously-skip-permissions"], "not accepted"),
    ],
)
def test_session_setting_says_unknown_when_argv_is_unreadable(
    monkeypatch, tmp_path, argv, expected
):
    monkeypatch.setattr(inbound.launch_args, "argv", lambda pid: argv)

    assert inbound.session_setting(session_socket.Session(1, "s", str(tmp_path), "")) == expected
