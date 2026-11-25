"""`lemonaid docs mode`: show or change an existing session's docs mode.

The change is recorded for the session (`mode.record`); what it changes, and when, is
up to the harness, so the command says.
"""

import os
import sys
from collections import abc

from .. import docs_config
from ..config import load_config
from . import mode, paths

_TAKES_EFFECT = {
    "claude": "when it is next resumed through lemonaid (lemon resume, the inbox, or"
    " `lemonaid claude --resume`). Until then it keeps the docs it started with, since"
    " Claude can't unload its system prompt or CLAUDE.md mid-session.",
    "codex": "at its next compaction or resume. A /clear starts a new thread in the mode"
    " it was launched with.",
}


def _self() -> tuple[str, str]:
    if session := os.environ.get("CLAUDE_CODE_SESSION_ID"):
        return "claude", session

    if session := os.environ.get("CODEX_THREAD_ID"):
        return "codex", session

    sys.exit("--self needs CLAUDE_CODE_SESSION_ID or CODEX_THREAD_ID")


def _recorded(wanted: str) -> tuple[str, str]:
    """The session with a recorded mode that *wanted*, a session ID, a prefix of one or a
    channel, names."""
    harness, _, session = wanted.rpartition(":")
    found = [
        tuple(path.name.split("-", 1))
        for path in sorted(paths.sessions().glob("*-*"))
        if path.is_file() and "." not in path.name
    ]
    matching = [(h, s) for h, s in found if s.startswith(session) and harness in ("", h)]
    if len(matching) != 1:
        sys.exit(
            f"{len(matching)} sessions with a docs mode match {wanted!r}"
            + (f": {', '.join(f'{h}:{s}' for h, s in matching)}" if matching else "")
        )
    return matching[0]


def run(words: abc.Sequence[str], own: bool) -> None:
    if own and len(words) <= 1:
        (harness, session), new = _self(), words[0] if words else ""
    elif not own and len(words) in (1, 2):
        (harness, session), new = _recorded(words[0]), words[1] if len(words) == 2 else ""
    else:
        sys.exit("usage: lemonaid docs mode (--self | SESSION) [classic|packages]")

    config = load_config().docs
    if not new:
        print(f"{harness} {session}: {mode.current(harness, session, '', config)}")
        return

    if new not in docs_config.MODES:
        sys.exit(f"docs mode must be one of {', '.join(docs_config.MODES)}, not {new!r}")
    mode.record(harness, session, new)
    effective = mode.usable(new, config)
    print(
        f"{harness} {session} takes docs mode {new} {_TAKES_EFFECT[harness]}"
        + (
            f" Without [docs] roots it gets {effective} until they are set."
            if effective != new
            else ""
        )
    )
