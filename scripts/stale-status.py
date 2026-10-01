#!/usr/bin/env python3
"""How often a Claude lemon keeps a Status that waits on Peter after he has answered it.

    scripts/stale-status.py                       # every briefed Claude session
    scripts/stale-status.py --since 2026-10-02    # only turns from that day on
    scripts/stale-status.py --list                # each counted turn, for an audit

lemonaid keeps no history of a brief's Status, so this rebuilds it from each
session's transcript: an Edit or Write of the brief (whose result holds the file
before the edit), a Read of it, and a Bash command that runs `brief status` or
writes a `Status:` line. Changes another lemon makes show up at this session's
next Edit or Read of the brief.

A turn is *answered* when it starts with the Status `blocked`, `alert` or
`merge`, its input is a prompt or an inbox message (a `lemonaid inbox watch`
task finishing), and the lemon works in it: two or more tool calls besides
re-arming waiters. It is *stale* when it ends with the Status unchanged and no
edit of the brief's Needs. A turn whose PostToolUse output carries the status
note, or that lemonaid's `status-notes.jsonl` lists by prompt ID, counts as *nudged*.

Reads the live database read-only and the transcripts under ~/.claude/projects.
"""

import argparse
import dataclasses
import datetime
import getpass
import json
import re
import sqlite3
import statistics
from collections import abc
from pathlib import Path

_DB = Path("~/.local/share/lemonaid/lemonaid.db").expanduser()
_PROJECTS = Path("~/.claude/projects").expanduser()
_NOTES = Path("~/.local/state/lemonaid/status-notes.jsonl").expanduser()
_WAITING_ON_PETER = {"blocked", "alert", "merge"}
_STATES = "working|running|waiting|blocked|alert|merge|review|done"
_STATUS_LINE = re.compile(rf"^Status:\s*({_STATES})\b", re.IGNORECASE | re.MULTILINE)
_STATUS_ANYWHERE = re.compile(rf"Status:\s*({_STATES})\b")
_STATUS_VERB = re.compile(rf"brief status\b[^\n;&|]*?\b({_STATES})\b")
_WAITER = re.compile(r"inbox watch|watch[- ](pr|doc|file)")
_NOTE = "Your brief's Status is `"
_ACTS = re.compile(r"\bgit (commit|push)\b|\bgh pr (create|ready|edit|comment)\b")
_TASK_OUTPUT = re.compile(r"/tasks/\S+\.output")
_SENDER = re.compile(r"^From: (\S+)")


@dataclasses.dataclass
class Turn:
    session: str
    start: datetime.datetime
    kind: str  # "prompt", "message" (from a lemon), "answer" (a message from Peter), or ""
    text: str
    status: str
    end_status: str = ""
    tool_calls: int = 0
    acted: bool = False  # edited a file other than the brief, committed, or pushed
    needs_edited: bool = False
    prompt_id: str = ""
    nudged: bool = False
    next_change: datetime.datetime | None = None


def _briefed_sessions(db: Path) -> dict[str, Path]:
    """Claude channel suffix (the session ID's first 8 characters) to its brief."""
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT channel, path FROM session_briefs WHERE channel LIKE 'claude:%'"
        )
        return {channel.split(":", 1)[1]: Path(path) for channel, path in rows}


def _time(entry: dict) -> datetime.datetime:
    return datetime.datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))


def _status(text: str) -> str:
    found = _STATUS_LINE.findall(text)
    return found[-1].lower() if found else ""


def _edited(tool: dict, result: dict) -> tuple[str, str]:
    """The brief before and after an Edit or Write, from the tool's input and result."""
    before = result.get("originalFile") or ""
    if tool["name"] == "Write":
        return before, tool["input"].get("content", "")

    old, new = tool["input"].get("old_string", ""), tool["input"].get("new_string", "")
    count = -1 if tool["input"].get("replace_all") else 1
    return before, before.replace(old, new, count)


def _needs(text: str) -> str:
    match = re.search(r"^#{3,}\s+Needs.*?(?=^#{2,}\s|\Z)", text, re.MULTILINE | re.DOTALL)
    return match.group(0).strip() if match else ""


def _turns(transcript: Path, session: str, brief: Path) -> abc.Iterator[Turn]:
    status, turn, prompt_id = "working", None, None
    tools: dict[str, dict] = {}
    changes: list[tuple[datetime.datetime, str]] = []
    all_turns: list[Turn] = []

    def change(when: datetime.datetime, new: str) -> None:
        nonlocal status
        if new and new != status:
            changes.append((when, new))
            status = new

    for line in transcript.open():
        entry = json.loads(line)
        kind = entry.get("type")
        if kind == "user" and isinstance(entry["message"]["content"], str):
            origin = (entry.get("origin") or {}).get("kind")
            if origin in {"human", "task-notification"} and entry.get("promptId") != prompt_id:
                prompt_id = entry.get("promptId")
                text = entry["message"]["content"]
                use = re.search(r"<tool-use-id>(\S+?)</tool-use-id>", text)
                command = (
                    tools.get(use.group(1), {}).get("input", {}).get("command", "") if use else ""
                )
                source = (
                    "prompt"
                    if origin == "human"
                    else ("message" if "inbox watch" in command else "")
                )
                turn = Turn(session, _time(entry), source, text[:160], status, prompt_id=prompt_id)
                all_turns.append(turn)
        elif kind == "assistant":
            for block in entry["message"].get("content") or []:
                if block.get("type") != "tool_use":
                    continue

                tools[block["id"]] = block
                command = block["input"].get("command", "") if block["name"] == "Bash" else ""
                if turn and not _WAITER.search(command) and not _TASK_OUTPUT.search(command):
                    turn.tool_calls += 1
                edits_other = block["name"] in {"Edit", "Write"} and (
                    Path(block["input"].get("file_path", "")).name != brief.name
                )
                if turn and (edits_other or _ACTS.search(command)):
                    turn.acted = True
                if command and (found := _STATUS_VERB.findall(command)):
                    change(_time(entry), found[-1])
                elif (
                    command
                    and brief.name in command
                    and (written := _STATUS_ANYWHERE.findall(command))
                ):
                    change(_time(entry), written[-1].lower())  # the last: replace()'s new value
                if turn and "brief bullet" in command and ("Needs" in command or " rm " in command):
                    turn.needs_edited = True
        elif kind == "user" and entry.get("toolUseResult") is not None:
            for block in entry["message"]["content"]:
                content = block.get("content") if isinstance(block, dict) else None
                sender = _SENDER.match(content) if isinstance(content, str) else None
                if turn and turn.kind == "message" and sender:
                    turn.kind = "answer" if sender.group(1) == getpass.getuser() else "message"

                tool = (
                    tools.get(block.get("tool_use_id", ""), {}) if isinstance(block, dict) else {}
                )
                path = tool.get("input", {}).get("file_path", "")
                if Path(path).name != brief.name:  # briefs moved from ~/.brief-lemons
                    continue

                result = entry["toolUseResult"]
                if not isinstance(result, dict):
                    continue  # an error

                if tool["name"] in {"Edit", "Write"}:
                    before, after = _edited(tool, result)
                    change(_time(entry), _status(before))
                    change(_time(entry), _status(after))
                    if turn and _needs(before) != _needs(after):
                        turn.needs_edited = True
                elif tool["name"] == "Read":
                    change(_time(entry), _status(result.get("file", {}).get("content", "")))
        elif kind == "attachment" and turn:
            attachment = entry.get("attachment") or {}
            shown = json.dumps([attachment.get("stdout"), attachment.get("content")])
            turn.nudged = turn.nudged or _NOTE in shown

        if turn:
            turn.end_status = status

    for turn in all_turns:
        turn.next_change = next((when for when, _ in changes if when > turn.start), None)
        yield turn


def _noted(log: Path) -> set[tuple[str, str]]:
    """(session ID, prompt ID) of each turn the status-note hook reminded."""
    if not log.is_file():
        return set()

    return {
        (note["session_id"], note["prompt_id"])
        for note in map(json.loads, log.read_text().splitlines())
    }


def _answered(turn: Turn) -> bool:
    return turn.status in _WAITING_ON_PETER and turn.kind != "" and turn.tool_calls >= 2


def _stale(turn: Turn) -> bool:
    return turn.end_status == turn.status and not turn.needs_edited


def _report(label: str, turns: list[Turn]) -> str:
    stale = [t for t in turns if _stale(t)]
    acted = [t for t in stale if t.acted]
    lags = [(t.next_change - t.start).total_seconds() / 60 for t in stale if t.next_change]
    rate = f"{len(stale) / len(turns):.0%}" if turns else "-"
    lag = f"median {statistics.median(lags):.0f} min until the next change" if lags else ""
    return (
        f"{label}: {len(stale)} of {len(turns)} answered turns stale ({rate}), "
        f"{len(acted)} of them changing files or a PR. {lag}"
    ).rstrip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=datetime.date.fromisoformat)
    parser.add_argument("--until", type=datetime.date.fromisoformat)
    parser.add_argument("--list", action="store_true", help="Print each answered turn")
    parser.add_argument("--db", type=Path, default=_DB)
    parser.add_argument("--projects", type=Path, default=_PROJECTS)
    parser.add_argument("--notes", type=Path, default=_NOTES, help="The status-note hook's log")
    args = parser.parse_args()

    turns: list[Turn] = []
    sessions = _briefed_sessions(args.db)
    for transcript in args.projects.glob("*/*.jsonl"):
        brief = sessions.get(transcript.stem[:8])
        if brief is not None and not brief.name.startswith("control-center"):  # always working
            turns.extend(_turns(transcript, transcript.stem, brief))

    noted = _noted(args.notes)
    for turn in turns:
        turn.nudged = turn.nudged or (turn.session, turn.prompt_id) in noted

    answered = [
        t
        for t in turns
        if _answered(t)
        and (not args.since or t.start.date() >= args.since)
        and (not args.until or t.start.date() < args.until)
    ]
    print(f"{len(sessions)} briefed Claude sessions, {len(turns)} turns.")
    print(_report("All", answered))
    for kind in ("prompt", "answer", "message"):
        print(_report(f"  input: {kind}", [t for t in answered if t.kind == kind]))
    print(_report("  nudged", [t for t in answered if t.nudged]))
    print(_report("  not nudged", [t for t in answered if not t.nudged]))

    if args.list:
        for t in sorted(answered, key=lambda t: t.start):
            flag = ("ACTED" if t.acted else "STALE") if _stale(t) else "ok   "
            print(
                f"{flag} {t.start:%m-%d %H:%M} {t.session[:8]} {t.status}->{t.end_status}"
                f" {t.kind:7} {t.tool_calls:3} tools  {' '.join(t.text.split())[:90]}"
            )


if __name__ == "__main__":
    main()
