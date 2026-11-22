"""The messages lemons ended their turns with, read back from both harnesses' transcripts.

Claude writes one transcript entry per content block. A turn ended with an assistant
message's text when no tool call followed it before the next user entry, or before the
system entry Claude writes when a turn ends (a turn a background task starts has no
user entry before it). Codex records
each finished turn's final message as a `task_complete` event. Spawned threads and
subagents are left out in both, as the Stop hook leaves them out.
"""

import datetime as dt
import json
import os
import typing as ty
from collections import abc
from pathlib import Path

from ..codex import daemon_setup
from ..log import get_logger

_log = get_logger("rules.transcripts")

_CLAUDE_TURN_ENDED = frozenset({"stop_hook_summary", "turn_duration"})


class Said(ty.NamedTuple):
    at: dt.datetime
    harness: str
    transcript: Path
    cwd: str
    text: str


def _entries(path: Path) -> abc.Iterator[dict]:
    try:
        with path.open() as lines:
            for line in lines:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict):
                    yield entry
    except OSError as error:
        _log.warning("cannot read %s: %s", path, error)


def _claude_text(entry: dict) -> abc.Iterator[str | None]:
    """Each text block's text, and None for each tool call, in an assistant entry."""
    for block in (entry.get("message") or {}).get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and str(block.get("text", "")).strip():
            yield block["text"]
        elif block.get("type") == "tool_use":
            yield None


def _claude_turn_ends(entries: abc.Iterable[dict]) -> abc.Iterator[tuple[dict, str]]:
    """(entry, text) for each assistant message a Claude turn ended with."""
    said: tuple[dict, str] | None = None
    for entry in entries:
        if entry.get("isSidechain") or entry.get("isApiErrorMessage"):
            continue

        if entry.get("type") == "assistant":
            for text in _claude_text(entry):
                same = said and said[0].get("message", {}).get("id") == entry["message"].get("id")
                said = None if text is None else (entry, f"{said[1]}\n\n{text}" if same else text)
        elif said and (
            entry.get("type") == "user"
            or (entry.get("type") == "system" and entry.get("subtype") in _CLAUDE_TURN_ENDED)
        ):
            yield said
            said = None
    if said:
        yield said


def _at(raw: object) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(raw)).astimezone()
    except ValueError:
        return None


def _claude(path: Path) -> abc.Iterator[Said]:
    for entry, text in _claude_turn_ends(_entries(path)):
        if at := _at(entry.get("timestamp")):
            yield Said(at, "claude", path, str(entry.get("cwd") or ""), text)


def _codex(path: Path) -> abc.Iterator[Said]:
    cwd = ""
    for entry in _entries(path):
        payload = entry.get("payload") or {}
        if entry.get("type") == "session_meta":
            if payload.get("parent_thread_id") or isinstance(payload.get("source"), dict):
                return  # a spawned thread

            cwd = str(payload.get("cwd") or "")
        elif entry.get("type") == "turn_context":
            cwd = str(payload.get("cwd") or cwd)
        elif (
            payload.get("type") == "task_complete"
            and isinstance(said := payload.get("last_agent_message"), str)
            and (at := _at(entry.get("timestamp")))
        ):
            yield Said(at, "codex", path, cwd, said)


def _recent(paths: abc.Iterable[Path], since: float) -> list[Path]:
    found = []
    for path in paths:
        try:
            if path.stat().st_mtime >= since:
                found.append(path)
        except OSError as error:
            _log.warning("cannot stat %s: %s", path, error)
    return found


def _claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def turn_ends(since: dt.datetime) -> abc.Iterator[Said]:
    """Every end-of-turn message since *since* in Claude's and Codex's transcripts."""
    cutoff = since.timestamp()
    claude = _recent((_claude_home() / "projects").glob("*/*.jsonl"), cutoff)
    codex_home = daemon_setup.codex_home()
    codex = _recent(
        (
            path
            for folder in ("sessions", "archived_sessions")
            for path in (codex_home / folder).rglob("rollout-*.jsonl")
        ),
        cutoff,
    )
    for read, paths in ((_claude, claude), (_codex, codex)):
        for path in paths:
            yield from (said for said in read(path) if said.at >= since)
