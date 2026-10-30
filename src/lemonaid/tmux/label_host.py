"""Tab labels as a scout host service: one label client thread per registered tmux server.

A client whose server is gone removes the server's registration; tmux registers it again
when it next loads its config. One that fails otherwise is tried again after
`RETRY_SECONDS`.
"""

import dataclasses
import threading
import time

from ..log import get_logger
from ..watch import host_services
from . import label_client, label_servers

_log = get_logger("tmux.label_host")

RETRY_SECONDS = 30.0


@dataclasses.dataclass
class Client:
    thread: threading.Thread
    outcome: label_client.Outcome = "stopped"


def _start(socket: str, quitting: threading.Event) -> Client:
    client = Client(threading.Thread())

    def body() -> None:
        try:
            client.outcome = label_client.run(socket, quitting)
        except Exception:  # the host outlives any one server's labels
            _log.exception("tmux labels for %s crashed", socket)
            client.outcome = "retry"

    client.thread = threading.Thread(target=body, name="tmux-labels", daemon=True)
    client.thread.start()
    return client


def tick(clients: dict[str, Client], retry_at: dict[str, float], quitting: threading.Event) -> int:
    """Make the running clients match the registered servers; how many servers there are."""
    wanted = label_servers.listed()
    for socket, client in list(clients.items()):
        if client.thread.is_alive():
            continue

        del clients[socket]
        if client.outcome == "gone":
            _log.info("tmux server %s is gone; no longer labelling it", socket)
            label_servers.remove(socket)
            wanted.discard(socket)
        elif client.outcome == "retry":
            retry_at[socket] = time.monotonic() + RETRY_SECONDS
    for socket in wanted:
        if socket not in clients and time.monotonic() >= retry_at.get(socket, 0):
            retry_at.pop(socket, None)
            clients[socket] = _start(socket, quitting)
    return len(wanted)


def service() -> host_services.Service:
    """Tab labels for the scout host to run."""
    clients: dict[str, Client] = {}
    retry_at: dict[str, float] = {}

    def join() -> None:
        for client in clients.values():
            client.thread.join(timeout=5)

    return host_services.Service(
        lambda quitting: tick(clients, retry_at, quitting),
        join,
        lambda: bool(label_servers.listed()),
    )
