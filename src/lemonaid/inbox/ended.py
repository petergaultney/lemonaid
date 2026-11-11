"""Why a lemon's inbox row stopped being a running lemon, kept on the row as `ended`.

`server-lost` and `crashed` leave the row active, for restore to bring back. Every
other cause goes with archiving the row. A row's next registration (`db.add`,
`db.register_working`) replaces its metadata, so a lemon heard from again has no
`ended`.
"""

import time
import typing as ty
from collections import abc

SERVER_LOST = "server-lost"  # its terminal server went away with it
USER_EXIT = "user-exit"  # the harness reported its own end
CRASHED = "crashed"  # its harness stopped unasked, while its pane and server run
PANE_CLOSED = "pane-closed"  # its pane went away on a server that still runs
PROCESS_EXITED = "process-exited"  # its pane lives, its harness doesn't
REPLACED = "replaced"  # another channel took over its session
TOSSED = "tossed"  # its place was torn down
ARCHIVED = "archived"  # someone archived it
DISMISSED = "dismissed"  # lost, and someone said not to bring it back

KEY = "ended"


def record(cause: str, by: str, detail: str = "", at: float | None = None) -> dict[str, ty.Any]:
    """The `ended` value to store on a row."""
    return {"at": time.time() if at is None else at, "cause": cause, "by": by, "detail": detail}


def reported(metadata: abc.Mapping[str, ty.Any]) -> str:
    """The cause a harness's own end report (`exit_reason`) gives, "" when it made none
    or its handler judged the end not deliberate (`exit_deliberate`): Claude reports a
    SIGTERM too, as `other`, which is how a row recorded before `exit_deliberate` is read.

    Claude reports `/clear` as an end, and the session that follows in the same
    process is the lemon now.
    """
    if "exit_reason" not in metadata or not metadata.get(
        "exit_deliberate", metadata["exit_reason"] not in ("", "other")
    ):
        return ""

    return REPLACED if metadata["exit_reason"] == "clear" else USER_EXIT


def cause(metadata: abc.Mapping[str, ty.Any]) -> str:
    """The recorded cause, "" when the row records none."""
    ended = metadata.get(KEY)
    return str(ended.get("cause") or "") if isinstance(ended, abc.Mapping) else ""


def lost(metadata: abc.Mapping[str, ty.Any]) -> bool:
    return cause(metadata) == SERVER_LOST


def revivable(metadata: abc.Mapping[str, ty.Any]) -> bool:
    """Whether the row is kept for restore: lost with its server, or its harness crashed."""
    return cause(metadata) in (SERVER_LOST, CRASHED)


def failed(metadata: abc.Mapping[str, ty.Any]) -> bool:
    """Whether a restore tried to bring the lemon back and could not."""
    return lost(metadata) and bool(metadata[KEY].get("failed"))
