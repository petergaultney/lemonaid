"""`lemonaid tmux labels` registers its server, and the scout host keeps its labels while it lives."""

import argparse
import shutil
import threading

import pytest

from lemonaid.tmux import label_host, label_servers, labels_cli, window_labels
from lemonaid.watch import host_services, scout_host, scout_start

from . import shared

pytestmark = pytest.mark.skipif(not shutil.which("tmux"), reason="needs tmux")


def test_registering_a_server_starts_the_host(monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(scout_start, "_spawn", lambda: started.append(True))

    labels_cli._cmd(argparse.Namespace(socket="/tmp/some.sock"))

    assert label_servers.listed() == {"/tmp/some.sock"} and started == [True]


def test_the_host_labels_a_registered_server_until_it_is_gone(monkeypatch):
    monkeypatch.setattr(scout_host, "_TICK", 0.05)
    with shared.server() as (socket, tmux):
        label_servers.register(socket)
        codes: list[int] = []
        host = threading.Thread(
            target=lambda: codes.append(
                scout_host.serve(lambda r, s: "ended", idle=0.3, services=(label_host.service,))
            )
        )
        host.start()

        shared.until(lambda: tmux("show-options", "-wqv", "-t", "work:0", window_labels.LABEL))
        assert host.is_alive()  # a labelled server keeps an otherwise idle host running

        tmux("kill-server")
        host.join(10)

    assert codes == [0] and label_servers.listed() == set()


def test_a_server_registered_while_the_host_stops_brings_it_back(monkeypatch):
    restarts: list[bool] = []
    monkeypatch.setattr(scout_host.restart, "restart", lambda: restarts.append(True))
    labels = label_host.service()

    def stopping_service() -> host_services.Service:
        def join() -> None:  # a tmux server registers after the host's last tick
            label_servers.register("/tmp/late.sock")
            labels.join()

        return host_services.Service(labels.tick, join, labels.pending)

    monkeypatch.setattr(label_host, "tick", lambda clients, retry_at, quitting: 0)

    assert scout_host.serve(lambda r, s: "ended", idle=0, services=(stopping_service,)) == 0
    assert restarts == [True]
