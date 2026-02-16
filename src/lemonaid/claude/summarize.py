"""Summarize Claude sessions with poor names using claude -p --model haiku."""

from __future__ import annotations

import json
import subprocess
import typing as ty
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..inbox import db
from ..log import get_logger
from . import find_project_path

_log = get_logger("claude.summarize")

_SUMMARY_PROMPT = (
    "Summarize this coding session in a brief phrase (5-10 words). "
    "Describe what was attempted or accomplished. "
    "Reply with ONLY the summary phrase, nothing else. No quotes, no explanation."
)

_MAX_SUMMARY_LEN = 100


class SummarizeResult(ty.NamedTuple):
    summarized: int
    skipped_no_transcript: int
    failed: int


def _find_transcript(session_id: str, cwd: str) -> Path | None:
    project_dir = find_project_path(cwd)
    if not project_dir:
        return None
    path = project_dir / f"{session_id}.jsonl"
    return path if path.exists() else None


def _extract_text(content: ty.Any) -> str | None:
    """Extract plain text from a message content field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts) if parts else None
    return None


def _read_first_messages(jsonl_path: Path, n: int = 5) -> list[str]:
    """Read first N user/assistant text messages from a JSONL transcript."""
    messages: list[str] = []
    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if len(messages) >= n:
                    break
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type")
                if entry_type not in ("user", "assistant"):
                    continue

                msg = entry.get("message", {})
                role = msg.get("role", "")
                content = msg.get("content")
                text = _extract_text(content)
                if not text:
                    continue

                label = "User" if role == "user" else "Assistant"
                messages.append(f"{label}: {text}")
    except OSError:
        pass
    return messages


def _build_prompt(messages: list[str]) -> str:
    transcript = "\n\n".join(messages)
    return f"{_SUMMARY_PROMPT}\n\n---\n\n{transcript}"


def summarize_one(transcript_path: Path) -> str | None:
    """Run claude -p --model haiku on a transcript. Returns summary or None."""
    messages = _read_first_messages(transcript_path)
    if not messages:
        return None

    prompt = _build_prompt(messages)
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "haiku", "--tools", ""],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            _log.warning("claude -p failed (rc=%d): %s", result.returncode, result.stderr[:200])
            return None
        summary = result.stdout.strip().strip('"').strip("'")
        if not summary or len(summary) > _MAX_SUMMARY_LEN:
            _log.warning("summary rejected (len=%d): %s", len(summary), summary[:200])
            return None
        return summary
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        _log.warning("claude -p error: %s", exc)
        return None


def _get_sessions_needing_summary(conn: db.sqlite3.Connection) -> list[db.Notification]:
    rows = conn.execute(
        """
        SELECT * FROM notifications
        WHERE status IN ('archived', 'read')
        AND json_extract(metadata, '$.name_source') = 'first_prompt'
        ORDER BY created_at DESC
        """
    ).fetchall()
    return [db.Notification.from_row(row) for row in rows]


def run_summarize(dry_run: bool = False, max_workers: int = 5) -> SummarizeResult:
    """Batch-summarize sessions with poor names."""
    with db.connect() as conn:
        sessions = _get_sessions_needing_summary(conn)

    if not sessions:
        return SummarizeResult(0, 0, 0)

    if dry_run:
        return SummarizeResult(len(sessions), 0, 0)

    # Build (notification, transcript_path) pairs, filtering out missing transcripts
    work: list[tuple[db.Notification, Path]] = []
    skipped_no_transcript = 0
    for n in sessions:
        session_id = n.metadata.get("session_id", "")
        cwd = n.metadata.get("cwd", "")
        path = _find_transcript(session_id, cwd) if session_id and cwd else None
        if path:
            work.append((n, path))
        else:
            skipped_no_transcript += 1

    if not work:
        return SummarizeResult(0, skipped_no_transcript, 0)

    summarized = 0
    failed = 0
    total = len(work)

    def _do_one(item: tuple[db.Notification, Path]) -> tuple[db.Notification, str | None]:
        n, path = item
        return n, summarize_one(path)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_do_one, item): item for item in work}
        for i, future in enumerate(as_completed(futures), 1):
            n, summary = future.result()
            short_id = n.metadata.get("session_id", "")[:8]
            if summary:
                with db.connect() as conn:
                    db.update_name(
                        conn,
                        n.id,
                        summary,
                        extra_metadata={"name_source": "lemonaid_forced_summary"},
                    )
                summarized += 1
                print(f'[{i}/{total}] "{summary}" <- {short_id}')
            else:
                failed += 1
                print(f"[{i}/{total}] FAILED <- {short_id}")

    return SummarizeResult(summarized, skipped_no_transcript, failed)
