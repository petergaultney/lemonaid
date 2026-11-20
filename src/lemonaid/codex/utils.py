"""Codex session utilities."""

import re


def extract_session_id_from_filename(name: str) -> str | None:
    """Extract a session UUID from a Codex session filename."""
    match = re.search(
        r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        name,
    )
    if match:
        return match.group(1)
    return None
