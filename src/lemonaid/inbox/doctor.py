"""What lemonaid knows about your running sessions, and what it could restore.

Most of what restore depends on is invisible until you need it - a location
recorded weeks ago, a hook that either fired or didn't. This reports the state
of that before a crash rather than after, which is the only time it is useful
to find out.
"""

import json
import subprocess
import typing as ty
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..claude import install_hooks
from ..inbox import db

_CLAUDE_PROCESSES = ("claude", "codex", "openclaw", "opencode")
_MIN_TRANSCRIPT_BYTES = 5000


@dataclass(frozen=True)
class Pane:
    session: str
    window: str
    tty: str
    command: str


def live_panes() -> list[Pane]:
    """Every pane on the current tmux server."""
    result = subprocess.run(
        [
            "tmux",
            "list-panes",
            "-a",
            "-F",
            "#{session_name}|#{window_index}|#{pane_tty}|#{pane_current_command}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    return [
        Pane(*parts)
        for line in result.stdout.strip().splitlines()
        if len(parts := line.split("|")) == 4
    ]


def _looks_like_a_lemon(command: str) -> bool:
    """Whether a pane is running an agent.

    Claude Code sets its process title to its own version number, so the name
    carries no hint of what it is - hence the digits-and-dots test rather than
    a list of names.
    """
    if command in _CLAUDE_PROCESSES:
        return True

    return command.replace(".", "").isdigit() and "." in command


def transcript_for(session_id: str) -> Path | None:
    """The transcript file for a session, if one exists on disk."""
    if not session_id:
        return None

    return next(Path.home().joinpath(".claude/projects").rglob(f"{session_id}.jsonl"), None)


def _known_sessions() -> list[tuple[str, str, dict]]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT name, status, metadata FROM notifications "
            "WHERE status IN ('unread', 'read') ORDER BY created_at DESC"
        ).fetchall()

    return [(r[0] or "", r[1], json.loads(r[2] or "{}")) for r in rows]


def _restorable(metadata: dict) -> tuple[bool, str]:
    """Whether this row could be restored, and what is missing if not."""
    session_id = metadata.get("session_id")
    if not session_id:
        return False, "no session_id"

    if not metadata.get("cwd"):
        return False, "no cwd"

    if transcript_for(session_id) is None:
        return False, "transcript not on disk"

    if not metadata.get("tmux_session"):
        return True, "restorable, but no recorded window (will not be placed)"

    return True, "restorable"


def report() -> list[str]:
    """Lines describing what is running, what is known, and what would restore."""
    panes = live_panes()
    lemons = [p for p in panes if _looks_like_a_lemon(p.command)]
    known = _known_sessions()
    known_ttys = {m.get("tty") for _, _, m in known if m.get("tty")}

    hook_installed = (
        "SessionStart" in json.loads(install_hooks.settings_path().read_text()).get("hooks", {})
        if install_hooks.settings_path().exists()
        else False
    )

    restorable = [m for _, _, m in known if _restorable(m)[0]]
    placed = [m for m in restorable if m.get("tmux_session")]

    lines = [
        "Coverage",
        f"  {len(lemons)} agent panes running on this tmux server",
        f"  {len(known)} sessions in the inbox",
        f"  {len([p for p in lemons if p.tty not in known_ttys])} running panes the inbox does not know about",
        "",
        "Restore",
        f"  {len(restorable)} of {len(known)} inbox sessions could be resumed",
        f"  {len(placed)} of those have a recorded tmux window to be placed in",
        "",
        "SessionStart hook",
        f"  {'installed' if hook_installed else 'NOT installed - run `lemonaid claude hooks`'}",
    ]

    if not hook_installed:
        lines += [
            "  Without it a session is recorded only once it speaks, so sessions",
            "  you have not talked to yet are invisible to restore.",
        ]

    missing = []
    for name, _status, metadata in known:
        ok, why = _restorable(metadata)
        if not ok:
            missing.append((name, why))

    if missing:
        lines += ["", "Not restorable"]
        lines += [f"  {name[:44]:<44} {why}" for name, why in missing]

    unknown = len([p for p in lemons if p.tty not in known_ttys])
    unplaced = len(restorable) - len(placed)
    todo = []

    if unknown or unplaced:
        fixes = []
        if unknown:
            fixes.append(f"{unknown} running panes not in the inbox")
        if unplaced:
            fixes.append(f"{unplaced} with no window recorded")
        todo.append(f"  lemonaid tmux adopt       # {', '.join(fixes)}")

    if not hook_installed:
        todo.append("  lemonaid claude hooks     # so new sessions record themselves")

    if any("transcript" in why for _name, why in missing):
        todo.append(
            "  (transcript gone: nothing to resume - resuming would start a fresh"
            " conversation, silently)"
        )

    if todo:
        lines += ["", "What to do", *dict.fromkeys(todo)]

    return lines


def unknown_panes() -> list[Pane]:
    """Agent panes with no inbox row, which a restore would not bring back."""
    known_ttys = {m.get("tty") for _, _, m in _known_sessions() if m.get("tty")}

    return [p for p in live_panes() if _looks_like_a_lemon(p.command) and p.tty not in known_ttys]


def _pane_cwd(pane: Pane) -> str | None:
    result = subprocess.run(
        [
            "tmux",
            "display-message",
            "-t",
            f"{pane.session}:{pane.window}",
            "-p",
            "#{pane_current_path}",
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def _newest_transcript_for(cwd: str) -> tuple[str, float] | None:
    """The most recently written transcript for a working directory.

    How a running pane is matched to a conversation. It is the best available
    signal and not a certain one: several panes can share a cwd, and nothing on
    disk records which pane a transcript belonged to. Recency decides, and the
    caller is told when it was a guess.
    """
    best: tuple[str, float] | None = None
    for path in Path.home().joinpath(".claude/projects").rglob("*.jsonl"):
        if path.stem.startswith("agent-"):
            continue

        try:
            if path.stat().st_size < _MIN_TRANSCRIPT_BYTES:
                continue

            with path.open() as f:
                for line in f:
                    try:
                        entry_cwd = json.loads(line).get("cwd")
                    except json.JSONDecodeError:
                        continue

                    if entry_cwd:
                        break
                else:
                    continue

            if entry_cwd != cwd:
                continue

            mtime = path.stat().st_mtime
        except OSError:
            continue

        if best is None or mtime > best[1]:
            best = (path.stem, mtime)

    return best


@dataclass(frozen=True)
class Adoption:
    pane: Pane
    cwd: str
    session_id: str
    contested: bool  # another pane shares this cwd, so the match is a guess


def plan_adoption() -> list[Adoption]:
    """Running panes the inbox does not know, matched to their conversations.

    A pane that is running is the one case where the missing facts can still be
    recovered: it is there to be asked. Sessions started before the SessionStart
    hook existed are exactly this, and would otherwise stay invisible until each
    one happened to notify.
    """
    panes = unknown_panes()
    cwd_by_pane = {}
    for pane in panes:
        cwd = _pane_cwd(pane)
        if cwd:
            cwd_by_pane[pane] = cwd

    shared = Counter(cwd_by_pane.values())
    found_by_pane = {}
    for pane, cwd in cwd_by_pane.items():
        found = _newest_transcript_for(cwd)
        if found:
            found_by_pane[pane] = (cwd, found[0])

    # Two panes landing on one transcript is the clearest sign the match is a
    # guess, and it is not visible from either pane alone: distinct directories
    # can still resolve to the same conversation. Sessions already in the inbox
    # count too - a conversation that is demonstrably running somewhere else is
    # not the one in this pane.
    claims = Counter(session_id for _cwd, session_id in found_by_pane.values())
    claims.update(
        metadata["session_id"]
        for _n, _s, metadata in _known_sessions()
        if metadata.get("session_id")
    )

    return [
        Adoption(
            pane,
            cwd,
            session_id,
            contested=shared[cwd] > 1 or claims[session_id] > 1,
        )
        for pane, (cwd, session_id) in found_by_pane.items()
    ]


def adopt(plans: ty.Iterable[Adoption]) -> int:
    """Put these sessions in the inbox as working. Returns how many were added."""
    added = 0
    with db.connect() as conn:
        for plan in plans:
            db.register_working(
                conn,
                channel=f"claude:{plan.session_id}",
                message=f"Adopted from {plan.pane.session}:{plan.pane.window}",
                name=Path(plan.cwd).name,
                metadata={
                    "session_id": plan.session_id,
                    "cwd": plan.cwd,
                    "tty": plan.pane.tty,
                    "tmux_session": plan.pane.session,
                    "tmux_window": plan.pane.window,
                    "adopted": True,
                },
                switch_source="tmux",
            )
            added += 1

    return added
