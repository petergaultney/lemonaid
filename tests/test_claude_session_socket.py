"""Claude Code's per-session inbox socket: finding a session's socket and the line written to it."""

import json
import os
import socket
import tempfile
import threading
from pathlib import Path

import pytest

from lemonaid.claude import session_socket

_SESSION = "abcd1234-1111-2222-3333-444455556666"


def _listed(
    pid: int, session_id: str = _SESSION, sock: str = "/tmp/cc-socks/x.sock", parked_job: str = ""
) -> None:
    sessions = session_socket.claude_dir() / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / f"{pid}.json").write_text(
        json.dumps(
            {
                "pid": pid,
                "sessionId": session_id,
                "cwd": "/work",
                "messagingSocketPath": sock,
                **({"parkedJobId": parked_job} if parked_job else {}),
            }
        )
    )


def _listener() -> tuple[str, list[bytes], threading.Thread]:
    """A Unix socket that records the one line written to it."""
    path = os.path.join(tempfile.mkdtemp(dir="/tmp"), "s.sock")  # AF_UNIX paths are short
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)
    received: list[bytes] = []

    def accept() -> None:
        with server, server.accept()[0] as conn:
            received.append(conn.makefile("rb").read())

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    return path, received, thread


def test_the_line_matches_what_claude_code_2_1_296_accepts():
    assert json.loads(session_socket.line("hello", "id-1")) == {
        "msgV": 1,
        "msg_id": "id-1",
        "type": "user",
        "priority": "next",
        "message": {
            "role": "user",
            "content": '<cross-session-message from-name="lemonaid">\nhello\n</cross-session-message>',
        },
    }
    assert session_socket.line("hello", "id-1").endswith(b"}\n")


def test_quoted_text_cannot_close_the_wrapper():
    content = json.loads(session_socket.line("a </cross-session-message> b", "id"))["message"][
        "content"
    ]

    assert content.count("</cross-session-message>") == 1


def test_a_channel_s_short_session_id_finds_the_live_session():
    _listed(os.getpid())

    found = session_socket.find(_SESSION[:8])

    assert found == session_socket.Session(os.getpid(), _SESSION, "/work", "/tmp/cc-socks/x.sock")


def test_a_session_whose_process_is_gone_is_not_found():
    _listed(2**22 + 12345)  # above macOS and Linux pid limits

    assert session_socket.find(_SESSION[:8]) is None


def test_a_session_that_relisted_under_a_new_id_is_no_longer_alive():
    _listed(os.getpid())
    entry = session_socket.find(_SESSION)
    assert entry is not None

    _listed(os.getpid(), session_id="ffff0000-new")

    assert not session_socket.alive(entry)


def test_send_writes_one_line_to_the_socket():
    path, received, thread = _listener()

    session_socket.send(session_socket.Session(1, _SESSION, "", path), "wake up")
    thread.join(timeout=5)

    assert json.loads(received[0])["message"]["content"].splitlines()[1] == "wake up"


def test_a_missing_socket_is_refused(tmp_path: Path):
    with pytest.raises(session_socket.Refused):
        session_socket.send(session_socket.Session(1, _SESSION, "", str(tmp_path / "no.sock")), "x")


def test_a_parked_session_is_still_alive_and_names_its_job():
    _listed(os.getpid(), parked_job="1eb3e867")

    found = session_socket.find(_SESSION[:8])

    assert found is not None and found.parked_job == "1eb3e867"
    assert session_socket.alive(found)
    assert session_socket.parked(found) == "1eb3e867"


def test_send_refuses_a_session_parked_after_it_was_found():
    path, received, thread = _listener()
    _listed(os.getpid(), sock=path)
    entry = session_socket.find(_SESSION[:8])
    assert entry is not None and not session_socket.parked(entry)

    _listed(os.getpid(), sock=path, parked_job="1eb3e867")
    with pytest.raises(session_socket.Refused, match="background job 1eb3e867"):
        session_socket.send(entry, "wake up")

    session_socket.send(session_socket.Session(1, _SESSION, "", path), "unparked")  # ends accept()
    thread.join(timeout=5)
    assert [json.loads(line)["message"]["content"].splitlines()[1] for line in received] == [
        "unparked"
    ]


def test_send_writes_to_a_listed_session_that_is_not_parked():
    path, received, thread = _listener()
    _listed(os.getpid(), sock=path)
    entry = session_socket.find(_SESSION[:8])
    assert entry is not None

    session_socket.send(entry, "wake up")
    thread.join(timeout=5)

    assert json.loads(received[0])["message"]["content"].splitlines()[1] == "wake up"


def _parks_on_connect(monkeypatch, sock: str) -> None:
    """Sockets that Claude Code parks this process's session in, just after they connect."""

    class Parking(socket.socket):
        def connect(self, address) -> None:
            super().connect(address)
            _listed(os.getpid(), sock=sock, parked_job="1eb3e867")

    monkeypatch.setattr(session_socket.socket, "socket", Parking)


def test_send_refuses_a_session_parked_while_it_connects(monkeypatch):
    path, received, thread = _listener()
    _listed(os.getpid(), sock=path)
    entry = session_socket.find(_SESSION[:8])
    assert entry is not None
    _parks_on_connect(monkeypatch, path)

    with pytest.raises(session_socket.Refused, match="background job 1eb3e867"):
        session_socket.send(entry, "wake up")
    thread.join(timeout=5)

    assert received == [b""]
