"""Opening the web client's gateway websocket with the user's session.

The URL holds the token, so nothing here puts it in an error or a log line: errors leave as
`Refused` or `OSError` naming only their kind.
"""

import contextlib
import logging
import typing as ty
import urllib.parse
from collections import abc

from . import session

try:  # the `slack` extra
    from websockets import exceptions as websocket_errors
    from websockets.sync import client as websocket_client
except ImportError:
    websocket_client = websocket_errors = None

_QUIET = logging.getLogger("lemonaid.slack.websockets")  # its debug lines would hold the URL
_QUIET.setLevel(logging.WARNING)


def available() -> bool:
    return websocket_client is not None


class Refused(OSError):
    """The gateway refused the socket's handshake."""


class Socket(ty.Protocol):
    def recv(self, timeout: float | None = None) -> str | bytes: ...

    def send(self, message: str) -> None: ...


Connect = abc.Callable[[str, str], ty.ContextManager[Socket]]


def url(current: session.Session) -> str:
    """The socket's URL, as the web client builds it. It holds the token: never log it."""
    start = urllib.parse.urlencode(
        {"agent": "client", "org_wide_aware": "true", "connect_only": "true", "ms_latest": "true"}
    )
    query = urllib.parse.urlencode(
        {
            "token": current.token,
            "sync_desync": "1",
            "slack_client": "desktop",
            "start_args": f"?{start}",
            "no_query_on_subscribe": "1",
            "flannel": "3",
            "lazy_channels": "1",
            "gateway_server": f"{current.enterprise_id or current.team_id}-1",
            "batch_presence_aware": "1",
        }
    )
    return f"wss://wss-primary.slack.com/?{query}"


@contextlib.contextmanager
def connect(address: str, cookie: str) -> abc.Iterator[Socket]:
    try:
        socket = websocket_client.connect(
            address,
            additional_headers={"Cookie": cookie},
            max_size=2**24,
            open_timeout=30,
            logger=_QUIET,
        )
    except websocket_errors.InvalidStatus as error:
        raise Refused(f"HTTP {error.response.status_code}") from None
    except websocket_errors.WebSocketException as error:
        raise OSError(type(error).__name__) from None
    with socket:
        try:
            yield socket
        except websocket_errors.WebSocketException as error:
            raise OSError(type(error).__name__) from None
