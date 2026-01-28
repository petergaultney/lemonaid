"""Slack ID mappings for deep linking.

Manages a JSON file that maps workspace/channel/user names to Slack IDs.
This enables constructing slack:// deep links from macOS notification data.

File structure:
{
  "Workspace Name": {
    "team_id": "T...",
    "channels": { "#channel-name": "C..." },
    "dms": { "User Name": "D..." }
  }
}

Mappings must be generated manually from Slack's browser IndexedDB.
See docs/macos.md for instructions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ChannelLookup:
    """Result of looking up a channel/DM."""

    team_id: str
    channel_id: str


def _get_default_path() -> Path:
    """Get the default path for the mappings file (in state folder)."""
    return Path.home() / ".local" / "state" / "lemonaid" / "slack-mappings.json"


def _resolve_path(path: Path | str | None) -> Path:
    """Resolve path to an absolute Path, using default if None."""
    return _get_default_path() if path is None else Path(path).expanduser()


def load_mappings(path: Path | str | None = None) -> dict:
    """Load mappings from file.

    Returns empty dict if file doesn't exist.
    """
    resolved = _resolve_path(path)

    if not resolved.exists():
        return {}

    try:
        with open(resolved) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def get_mappings_path() -> Path:
    """Get the path where mappings are stored."""
    return _get_default_path()


def lookup_channel(
    mappings: dict,
    workspace_name: str,
    channel_name: str,
) -> ChannelLookup | None:
    """Look up channel ID from workspace and channel name.

    Args:
        mappings: Loaded mappings dict
        workspace_name: Name of the workspace (from notification title)
        channel_name: Channel or user name (from notification subtitle)

    Returns:
        ChannelLookup with team_id and channel_id, or None if not found
    """
    workspace = mappings.get(workspace_name)
    if not workspace:
        return None

    team_id = workspace.get("team_id", "")
    if not team_id:
        return None

    channels = workspace.get("channels", {})
    dms = workspace.get("dms", {})

    # Try channels (with and without # prefix)
    channel_id = channels.get(channel_name)
    if not channel_id and not channel_name.startswith("#"):
        channel_id = channels.get(f"#{channel_name}")
    if not channel_id and channel_name.startswith("#"):
        channel_id = channels.get(channel_name[1:])

    # Try DMs
    if not channel_id:
        channel_id = dms.get(channel_name)

    if not channel_id:
        return None

    return ChannelLookup(team_id=team_id, channel_id=channel_id)
