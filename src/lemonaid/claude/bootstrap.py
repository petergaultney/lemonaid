"""Retroactively import historical Claude sessions into the lemonaid archive.

Sessions created before lemonaid was installed (or before hooks were configured)
are invisible to lemonaid's history view. This module scans Claude's
sessions-index.json files and imports them as archived notifications.
"""

from __future__ import annotations

import json
import typing as ty
from pathlib import Path

from ..inbox.channel import channel_id
from ..lemon_watchers import shorten_path
from ..log import get_logger

_log = get_logger("claude.bootstrap")

_NAME_MAX_LEN: ty.Final = 80


class _IndexEntry(ty.NamedTuple):
    session_id: str
    channel: str
    name: str
    message: str
    metadata: dict[str, ty.Any]
    created_at: float


class _ScanResult(ty.NamedTuple):
    entries: list[_IndexEntry]
    skipped_sidechain: int


class BootstrapResult(ty.NamedTuple):
    imported: list[_IndexEntry]
    skipped_existing: int
    skipped_sidechain: int


def _session_name(entry: dict) -> tuple[str, str]:
    """Derive a display name and its source from a sessions-index entry.

    Priority: customTitle > summary > firstPrompt (truncated).
    Returns (name, name_source).
    """
    if title := entry.get("customTitle"):
        return title, "custom_title"
    if summary := entry.get("summary"):
        return summary, "summary"
    if prompt := entry.get("firstPrompt"):
        truncated = prompt[:_NAME_MAX_LEN] + ("..." if len(prompt) > _NAME_MAX_LEN else "")
        return truncated, "first_prompt"
    return "Untitled session", "first_prompt"


def _parse_created_at(entry: dict) -> float:
    """Extract a unix timestamp from `created` (ISO 8601) or `fileMtime` (ms)."""
    if created := entry.get("created"):
        from datetime import datetime

        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            return dt.timestamp()
        except (ValueError, TypeError):
            pass
    if mtime := entry.get("fileMtime"):
        try:
            return float(mtime) / 1000.0
        except (ValueError, TypeError):
            pass
    return 0.0


def _entry_to_index_entry(entry: dict, cwd: str) -> _IndexEntry | None:
    """Convert one sessions-index entry to an _IndexEntry. Returns None if unusable."""
    session_id = entry.get("sessionId", "")
    if not session_id:
        return None

    name, name_source = _session_name(entry)
    channel = channel_id("claude", session_id)
    message = f"Session in {shorten_path(cwd)}"

    metadata: dict[str, ty.Any] = {
        "cwd": cwd,
        "session_id": session_id,
        "name_source": name_source,
    }
    if branch := entry.get("gitBranch"):
        metadata["git_branch"] = branch

    created_at = _parse_created_at(entry)

    return _IndexEntry(
        session_id=session_id,
        channel=channel,
        name=name,
        message=message,
        metadata=metadata,
        created_at=created_at,
    )


def _scan_session_indices() -> _ScanResult:
    """Glob all sessions-index.json files and extract importable entries."""
    claude_projects = Path.home() / ".claude" / "projects"
    if not claude_projects.is_dir():
        return _ScanResult([], 0)

    entries: list[_IndexEntry] = []
    skipped_sidechain = 0
    for index_path in claude_projects.glob("*/sessions-index.json"):
        try:
            data = json.loads(index_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            _log.warning("skipping %s: %s", index_path, exc)
            continue

        original_path = data.get("originalPath", "")

        for raw_entry in data.get("entries", []):
            if raw_entry.get("isSidechain"):
                skipped_sidechain += 1
                continue

            cwd = raw_entry.get("projectPath") or original_path
            if not cwd:
                continue

            parsed = _entry_to_index_entry(raw_entry, cwd)
            if parsed is not None:
                entries.append(parsed)

    return _ScanResult(entries, skipped_sidechain)


def _filter_existing(
    entries: list[_IndexEntry],
    existing_channels: set[str],
) -> tuple[list[_IndexEntry], int]:
    """Partition entries into importable vs already-tracked.

    Returns (imported, skipped_existing_count).
    """
    imported: list[_IndexEntry] = []
    seen = existing_channels.copy()
    skipped_existing = 0

    for entry in entries:
        if entry.channel in seen:
            skipped_existing += 1
        else:
            imported.append(entry)
            seen.add(entry.channel)

    return imported, skipped_existing


def run_bootstrap(dry_run: bool = False) -> BootstrapResult:
    """Scan Claude session indices and import historical sessions into lemonaid."""
    from ..inbox import db

    entries_found, skipped_sidechain = _scan_session_indices()

    with db.connect() as conn:
        rows = conn.execute("SELECT DISTINCT channel FROM notifications").fetchall()
        existing_channels = {row["channel"] for row in rows}

        imported, skipped_existing = _filter_existing(entries_found, existing_channels)
        result = BootstrapResult(
            imported=imported,
            skipped_existing=skipped_existing,
            skipped_sidechain=skipped_sidechain,
        )

        if dry_run or not result.imported:
            return result

        for entry in result.imported:
            db.add(
                conn,
                channel=entry.channel,
                message=entry.message,
                name=entry.name,
                metadata=entry.metadata,
                upsert=False,
                created_at=entry.created_at,
                status="archived",
            )

    _log.info(
        "bootstrap: imported=%d, skipped_existing=%d, skipped_sidechain=%d",
        len(result.imported),
        result.skipped_existing,
        result.skipped_sidechain,
    )
    return result
