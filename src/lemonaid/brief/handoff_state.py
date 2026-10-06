"""Persistent readiness and channel state for a brief moving between harnesses."""

import hashlib
import re
import secrets
import sqlite3
import time
from pathlib import Path

from . import check, handoff_claude

_PHRASE = re.compile(r"^lemonaid handoff (ready|accept) ([0-9a-f]{24})$")


def section(text: str) -> str:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == "## Handoff"), None)
    if start is None:
        return ""

    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).strip()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def request(
    conn: sqlite3.Connection,
    path: Path,
    source: str,
    harness: str,
    session: str,
    window: str,
    window_id: str,
    pane_id: str,
    source_command: str,
    deadline: float,
) -> sqlite3.Row:
    existing = conn.execute(
        "SELECT * FROM brief_handoffs WHERE path = ? AND phase NOT IN ('complete', 'failed')",
        (str(path),),
    ).fetchone()
    if existing:
        if existing["source"] != source or existing["harness"] != harness:
            raise ValueError("A different handoff is already pending for this brief")

        if deadline > existing["deadline"]:
            conn.execute(
                "UPDATE brief_handoffs SET deadline = ?, error = '' WHERE token = ?",
                (deadline, existing["token"]),
            )
            conn.commit()
            return get(conn, existing["token"])

        return existing

    token = secrets.token_hex(12)
    conn.execute(
        """INSERT INTO brief_handoffs
           (token, path, source, harness, phase, section_hash, session, source_window,
            source_window_id, source_pane_id, source_command, created_at, deadline)
           VALUES (?, ?, ?, ?, 'requested', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            token,
            str(path),
            source,
            harness,
            digest(section(path.read_text())),
            session,
            window,
            window_id,
            pane_id,
            source_command,
            time.time(),
            deadline,
        ),
    )
    conn.commit()
    return conn.execute("SELECT * FROM brief_handoffs WHERE token = ?", (token,)).fetchone()


def get(conn: sqlite3.Connection, token: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM brief_handoffs WHERE token = ?", (token,)).fetchone()
    if row is None:
        raise ValueError("No handoff has that token")

    return row


def ready(conn: sqlite3.Connection, row: sqlite3.Row) -> tuple[bool, str]:
    path = Path(row["path"])
    try:
        first = path.read_text()
        stat = path.stat()
        time.sleep(0.1)
        if path.stat().st_mtime_ns != stat.st_mtime_ns or path.read_text() != first:
            return False, "brief file is still changing"
    except OSError:
        return False, "brief file is unavailable"

    handoff = section(first)
    if not handoff or digest(handoff) == row["section_hash"]:
        return False, "## Handoff has not changed"

    if problems := [*check.structure(first), *check.recorded(conn, path, first)]:
        return False, "brief check failed: " + "; ".join(problems)

    if not handoff.splitlines() or handoff.splitlines()[-1] != f"Handoff-Ready: {row['token']}":
        if row["source"].startswith("claude:"):
            reply_has_marker = handoff_claude.has_ready_marker(conn, row)
        elif row["source"].startswith("codex:"):
            # Imported here to avoid a module cycle: handoff_codex also reads
            # typed handoff phrases through handoff_state.
            from . import handoff_codex

            reply_has_marker = handoff_codex.has_ready_marker(conn, row)
        else:
            reply_has_marker = False
        if not reply_has_marker:
            return False, "## Handoff is written but has no matching end marker"

    return True, ""


def pending_source(conn: sqlite3.Connection, path: Path, channel: str, now: float) -> bool:
    return (
        conn.execute(
            """SELECT 1 FROM brief_handoffs
               WHERE path = ? AND source = ? AND phase IN ('requested', 'prepared', 'launched')
                 AND error = '' AND deadline > ?""",
            (str(path), channel, now),
        ).fetchone()
        is not None
    )


def bind_target(conn: sqlite3.Connection, token: str, channel: str) -> bool:
    row = conn.execute("SELECT * FROM brief_handoffs WHERE token = ?", (token,)).fetchone()
    if row is None:
        return False

    if row["phase"] not in ("prepared", "launched") or not channel.startswith(row["harness"] + ":"):
        return False

    if row["target"] and row["target"] != channel:
        return False

    if not row["target"]:
        conn.execute("UPDATE brief_handoffs SET target = ? WHERE token = ?", (channel, token))
        conn.commit()

    return True


def acknowledge(conn: sqlite3.Connection, token: str, channel: str, action: str) -> str:
    row = get(conn, token)
    if row["phase"] in ("complete", "failed"):
        return row["phase"]

    if action == "ready":
        if channel != row["source"]:
            raise ValueError("Ready must come from the outgoing channel")
        good, reason = ready(conn, row)
        if not good:
            raise ValueError(reason)
        conn.execute("UPDATE brief_handoffs SET ready = 1 WHERE token = ?", (token,))
    elif action == "accept":
        if channel != row["target"] or not channel:
            raise ValueError("Accept must come from the reserved new channel")
        conn.execute("UPDATE brief_handoffs SET accepted = 1 WHERE token = ?", (token,))
    else:
        raise ValueError("Unknown handoff acknowledgement")

    conn.commit()
    return action


def typed_message(conn: sqlite3.Connection, channel: str, message: str) -> bool:
    match = _PHRASE.fullmatch(message.strip())
    if match is None:
        return False

    try:
        acknowledge(conn, match[2], channel, match[1])
    except ValueError:
        return False

    return True
