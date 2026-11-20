"""A trial log of the user's Slack presence while the gateway's socket is up, beside how long the
Mac has been idle: whether an idle socket keeps the user "active", and so holds back the phone
notifications Slack sends only to an away user.

Each line of `slack/presence.jsonl` is one `users.getPresence` reading. If idle time grows while
presence stays active, `[slack] push = false` fetches on a timer instead.
"""

import json
import re
import subprocess
import time

from ..log import get_logger
from . import api, session, wakes

_log = get_logger("slack.presence")
_IDLE = re.compile(rb'"HIDIdleTime" = (\d+)')


def _idle_seconds() -> float | None:
    try:
        found = _IDLE.search(
            subprocess.run(
                ["ioreg", "-c", "IOHIDSystem", "-d", "4"], capture_output=True, timeout=10
            ).stdout
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    return int(found[1]) / 1e9 if found else None


def record(current: session.Session) -> None:
    try:
        body = api.call(current, "users.getPresence", user=current.user_id)
    except (api.Failed, api.Unavailable) as error:
        _log.info("no presence reading: %s", error)
        return

    line = {
        "at": time.time(),
        "idle_seconds": _idle_seconds(),
        **{
            key: body.get(key)
            for key in ("presence", "online", "auto_away", "manual_away", "connection_count")
        },
    }
    with (wakes.state_dir() / "presence.jsonl").open("a") as log:
        log.write(json.dumps(line) + "\n")
