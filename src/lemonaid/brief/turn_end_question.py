"""Derive an inbox ask from a turn's final paragraph."""

import json
import re
import sqlite3
from pathlib import Path

from ..log import get_logger
from . import attached, status

_log = get_logger("brief.turn_end_question")
METADATA_KEY = "turn_end_question"


def last_paragraph(message: str) -> str:
    paragraphs = re.split(r"\n\s*\n", message.strip())
    paragraph = paragraphs[-1].strip() if paragraphs else ""
    return paragraph if "?" in paragraph else ""


def claude_final_message(path: Path) -> str:
    """Use the last assistant text entry in Claude's transcript at Stop."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""

    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = entry.get("message", {}).get("content", [])
        if isinstance(content, list):
            texts = [block.get("text", "") for block in content if block.get("type") == "text"]
            if texts:
                return "\n".join(texts)

    return ""


def add_ask(conn: sqlite3.Connection, channel: str, message: str, metadata: dict[str, str]) -> str:
    paragraph = last_paragraph(message)
    if not paragraph:
        return ""

    attached.claim_pending(conn)
    path = attached.by_channel(conn, [channel]).get(channel)
    if not path:
        return ""

    try:
        brief_status = status.split(path.read_text()).status
    except OSError:
        return ""
    if brief_status == "blocked":
        return ""

    metadata[METADATA_KEY] = paragraph
    _log.info("turn-end question: channel=%s brief=%s ask=%r", channel, path, paragraph)
    return paragraph


def by_brief(conn: sqlite3.Connection) -> dict[Path, str]:
    return {
        item.path: item.notification.metadata[METADATA_KEY]
        for item in attached.everything(conn)
        if item.notification and item.notification.metadata.get(METADATA_KEY)
    }
