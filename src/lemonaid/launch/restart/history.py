"""Fresh native transcript checks, independent of the inbox's last poll."""

import json
from collections import abc
from pathlib import Path

import lemonaid.claude.watcher
import lemonaid.codex.watcher


def entries(path: Path) -> list[dict]:
    result = []
    with path.open() as transcript:
        for line in transcript:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                result.append(entry)
    return result


def check(
    path: Path,
    session: str,
    turn_open: abc.Callable[[abc.Iterable[dict]], bool | None],
    force: bool,
) -> None:
    records = entries(path)
    identities = {
        str(
            entry.get("sessionId")
            or (entry.get("payload", {}).get("id") if entry.get("type") == "session_meta" else "")
        )
        for entry in records
    } - {""}
    if session not in identities or identities != {session}:
        raise ValueError("Transcript does not unambiguously belong to the full native session")
    if not force and turn_open(reversed(records)) is not False:
        raise ValueError(
            "Native transcript does not confirm an idle turn; use --force to interrupt"
        )


def validate(path: Path, session: str, harness: str, force: bool) -> None:
    check(
        path,
        session,
        lemonaid.claude.watcher.turn_open
        if harness == "claude"
        else lemonaid.codex.watcher.turn_open,
        force,
    )
