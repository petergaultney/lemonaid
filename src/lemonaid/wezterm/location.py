"""Where in WezTerm the calling hook's lemon runs, as inbox row metadata.

Recorded while the lemon runs, because once its pane closes nothing else says
which workspace and WezTerm instance to resume it in.
"""

import os
import typing as ty

from . import client


def metadata() -> dict[str, ty.Any]:
    """{} outside WezTerm, or when WezTerm can't place the caller's pane."""
    pane = os.environ.get("WEZTERM_PANE", "")
    if not pane.isdigit():
        return {}

    socket = os.environ.get(client.SOCKET_ENV) or None
    found = next((p for p in client.panes(socket) or [] if p.get("pane_id") == int(pane)), None)
    if found is None or not found.get("workspace"):
        return {}

    return {
        "wezterm_pane": int(pane),
        "wezterm_workspace": found["workspace"],
        **({"wezterm_socket": socket} if socket else {}),
    }
