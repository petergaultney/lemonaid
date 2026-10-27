"""Validate the pane identity used by direct jumps and their availability labels."""

import typing as ty

QUERY = (
    "list-panes",
    "-a",
    "-F",
    "#{pane_id}|#{pane_tty}|#{session_name}|#{session_created}|#{start_time}|#{session_id}",
)


def require_identity(metadata: dict[str, ty.Any]) -> None:
    if not all(metadata.get(key) for key in ("tty", "tmux_pane_identity", "tmux_session_order")):
        raise LookupError("No recorded tmux pane identity; wait for its next notification")


def resolve(metadata: dict[str, ty.Any], panes: str) -> str:
    tty = metadata.get("tty")
    recorded_pane = metadata.get("tmux_pane_identity")
    order = metadata.get("tmux_session_order")
    require_identity(metadata)

    matches: set[str] = set()
    for line in panes.splitlines():
        parts = line.split("|")
        if len(parts) != 6 or parts[1] != tty:
            continue

        pane, _, _, created, started, session_id = parts
        try:
            current_order = [int(created), int(started), int(session_id.lstrip("$"))]
        except ValueError:
            continue

        if [pane, current_order[1]] != recorded_pane or current_order != list(order):
            continue

        matches.add(pane)
    if len(matches) != 1:
        raise LookupError("Recorded tmux pane is gone or ambiguous; no jump made")

    return matches.pop()
