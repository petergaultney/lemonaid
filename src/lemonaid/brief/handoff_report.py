"""Status shown while a tokened harness handoff is pending."""

import shlex
from pathlib import Path

from ..config import load_config
from ..launch import command
from . import handoff_launch


def build(row) -> dict:
    manual = not row["source_pane_id"]
    report = {
        "token": row["token"],
        "phase": row["phase"],
        "source": row["source"],
        "target": row["target"] or None,
        "old_window": f"{row['session']}:{row['source_window']}" if not manual else None,
        "new_window": f"{row['session']}:{row['target_window']}" if row["target_window"] else None,
        "old_pane": row["source_pane_id"] or None,
        "new_pane": row["target_pane_id"] or None,
        "ready_phrase": f"lemonaid handoff ready {row['token']}",
        "accept_phrase": f"lemonaid handoff accept {row['token']}",
        "missing": [row["error"]] if row["phase"] == "failed" and row["error"] else [],
    }
    if row["resume_line"] and row["resume_cwd"]:
        report["resume_command"] = f"cd {shlex.quote(row['resume_cwd'])} && {row['resume_line']}"
    if manual and row["phase"] in ("launched", "transferred", "complete"):
        prompt = (
            f"Read {row['path']}, especially ## Handoff. Rearm ## Waiters, then run "
            f"lemonaid brief handoff accept {row['token']}. "
            "Your brief will attach only after that acknowledgement."
        )
        report["start_prompt"] = prompt
        typed, _ = command.harness_line(
            handoff_launch.configured_line(row["harness"], row["harness"]),
            Path(row["source_command"]),
            writable=command.codex_writable_roots(load_config().tmux_session),
        )
        report["start_command"] = (
            f"cd {shlex.quote(row['source_command'])} && "
            f"export LEMONAID_HANDOFF_TOKEN={shlex.quote(row['token'])} && "
            f"{typed} "
            f"{shlex.quote(prompt)}"
        )
    return report
