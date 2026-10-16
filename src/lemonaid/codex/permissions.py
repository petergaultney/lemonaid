"""Distinguish automatic approval review from a request for user attention."""

import json
from pathlib import Path

from ..log import get_logger

_log = get_logger("codex.permissions")


def automatically_reviewed(session_path: Path | None, turn_id: str, tool_name: str) -> bool:
    """Use the requesting turn's context, never another turn's or global config.

    PermissionRequest runs before the approval reviewer decides. Its hook input
    does not identify the reviewer. Shell and patch requests use the turn's
    reviewer; app calls can override it, so their notices must stay visible.
    """
    if tool_name not in ("Bash", "apply_patch") or not session_path or not turn_id:
        return False

    reviewer = ""
    try:
        with session_path.open(encoding="utf-8", errors="replace") as session:
            for line in session:
                if '"turn_context"' not in line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(entry, dict) or entry.get("type") != "turn_context":
                    continue

                context = entry.get("payload")
                if isinstance(context, dict) and context.get("turn_id") == turn_id:
                    reviewer = context.get("approvals_reviewer")
    except OSError:
        _log.warning("could not read approval reviewer from %s", session_path, exc_info=True)
        return False

    return reviewer == "auto_review"
