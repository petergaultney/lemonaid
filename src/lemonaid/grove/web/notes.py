"""The web grove's log of what browsers did, for finding out afterward why a page misbehaved.

One JSON object per line in `logs/web-grove.jsonl` under lemonaid's state directory: what each
page reports about itself (its screen, its errors, the views it saves, the keys it acted on) and
the calls it made that failed, ran slow, or changed something. It never holds what was typed to a
lemon. At *_MAX_BYTES* the file moves to `web-grove.jsonl.1`, replacing the one before.
"""

import json
import os
import threading
import time
from pathlib import Path

_MAX_BYTES = 2_000_000
_ASKED_OFTEN = frozenset(
    {"data", "lemon", "talk", "block_refusal", "search"}
)  # every few seconds, or each step of a drag or keystroke of a search: noted only when slow or failing
_SLOW_SECONDS = 1.0
_KEPT_ARGS = frozenset({"keep"})  # the page's saved views: small, and what a stuck view comes from
_lock = threading.Lock()


def path() -> Path:
    state = Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid").expanduser()
    return state / "logs" / "web-grove.jsonl"


def write(event: dict, client: str) -> None:
    line = json.dumps({"at": round(time.time(), 3), "client": client, **event}, default=str)
    found = path()
    with _lock:
        found.parent.mkdir(parents=True, exist_ok=True)
        if found.exists() and found.stat().st_size > _MAX_BYTES:
            found.replace(found.with_name(found.name + ".1"))
        with found.open("a") as out:
            out.write(line[:20_000] + "\n")


def call(name: str, seconds: float, error: str, client: str, args: object = None) -> None:
    """Note a call the page made, unless it's one asked often that went well."""
    if name in _ASKED_OFTEN and not error and seconds < _SLOW_SECONDS:
        return

    write(
        {
            "kind": "call",
            "call": name,
            "ms": round(seconds * 1000),
            **({"error": error} if error else {}),
            **({"args": args} if name in _KEPT_ARGS else {}),
        },
        client,
    )
