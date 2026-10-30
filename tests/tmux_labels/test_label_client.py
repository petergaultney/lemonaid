"""The label client keeps every window's label option current on a private tmux server."""

import shutil
import tempfile
import threading
from pathlib import Path

import pytest

from lemonaid.tmux import label_client, label_session, window_labels

from . import shared

pytestmark = pytest.mark.skipif(not shutil.which("tmux"), reason="needs tmux")


@pytest.fixture
def server():
    with shared.server() as found:
        yield found


def _label(tmux, target: str, option: str = window_labels.LABEL) -> str:
    return tmux("show-options", "-wqv", "-t", target, option)


def test_windows_are_labelled_and_relabelled_as_they_change(server):
    socket, tmux = server
    stop = threading.Event()
    outcome: list[str] = []
    client = threading.Thread(target=lambda: outcome.append(label_client.run(socket, stop)))
    client.start()
    try:
        shared.until(lambda: "sleep" in _label(tmux, "work:0"))  # once the shell has exec'd it
        assert "tmp" in _label(tmux, "work:0") and _label(
            tmux, "work:0", window_labels.CURRENT_LABEL
        )

        tmux("new-window", "-t", "work", "-c", "/usr", "sleep", "600")
        shared.until(lambda: "usr" in _label(tmux, "work:1"))

        assert window_labels.SUBSCRIPTION and label_client.SESSION in tmux(
            "list-sessions", "-F", "#{session_name}"
        )
        assert "work" not in tmux("list-clients", "-F", "#{session_name}")
    finally:
        stop.set()
        client.join(10)
    assert outcome == ["stopped"]


def test_the_client_reports_its_server_gone(server):
    socket, tmux = server
    outcome: list[str] = []
    client = threading.Thread(
        target=lambda: outcome.append(label_client.run(socket, threading.Event()))
    )
    client.start()
    shared.until(lambda: _label(tmux, "work:0"))

    tmux("kill-server")

    client.join(10)
    assert outcome == ["gone"]


def test_a_listing_queued_behind_label_writes_still_reaches_relabelling(server, monkeypatch):
    socket, _ = server
    session = label_session.Session(label_client._attach(socket, None))
    listings: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(session, "listed", lambda kind, lines: listings.append((kind, lines)))
    serving = threading.Thread(target=label_client._serve, args=(session,), daemon=True)
    serving.start()
    shared.until(lambda: session.listing)  # attached, and its own first listing is out
    window = window_labels.Window("@0", "", "/tmp", "sleep", "1", "")

    session.relabel(["\t".join(window)])  # two option writes for the window
    session.listing.clear()
    session.ask("windows")
    session.send("detach-client")
    serving.join(10)

    assert not serving.is_alive()
    session.process.wait(5)

    _, (kind, queued) = listings  # the client's own first listing, then the queued one
    assert kind == "windows" and any(line.startswith("@0\t") for line in queued)


def test_a_stale_registration_never_starts_a_server():
    with tempfile.TemporaryDirectory(prefix="tl-", dir="/tmp") as directory:  # short: socket paths
        socket = Path(directory) / "gone.sock"

        assert label_client.run(str(socket), threading.Event()) == "gone"
        assert not socket.exists()


def test_stopping_removes_the_helper_session(server):
    socket, tmux = server
    stop = threading.Event()
    client = threading.Thread(target=lambda: label_client.run(socket, stop))
    client.start()
    shared.until(lambda: _label(tmux, "work:0"))

    stop.set()
    client.join(10)

    assert tmux("list-sessions", "-F", "#{session_name}") == "work"
