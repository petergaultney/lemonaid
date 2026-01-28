"""macOS notification handler.

This module handles notifications from the macOS notification watcher daemon,
adding them to the lemonaid inbox.

The watcher daemon calls:
    lemonaid macos notify --app <bundle_id> --title "..." --body "..." --ax-id <uuid>

Slack integration requires configuration. Without a mappings file configured,
Slack notifications are silently ignored. This allows users to opt-in to
Slack integration by providing the mappings file.
"""

from ..config import load_config
from ..inbox import db

SLACK_BUNDLE_ID = "com.tinyspeck.slackmacgap"


def _get_slack_config():
    """Get Slack config if enabled, else None."""
    config = load_config()
    # Slack is enabled if [slack] section exists in config
    if config.slack.enabled:
        return config.slack
    return None


def _is_already_seen_and_read(conn: db.sqlite3.Connection, ax_id: str) -> bool:
    """Check if we've already processed this macOS notification and user marked it read.

    Returns True if we should skip this notification (don't resurface it).
    """
    if not ax_id:
        return False

    # Look for any notification with this ax_id in metadata that's been read
    row = conn.execute(
        """
        SELECT status FROM notifications
        WHERE json_extract(metadata, '$.ax_id') = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (ax_id,),
    ).fetchone()

    return bool(row and row["status"] == "read")


def handle_notification(
    app_bundle_id: str,
    title: str,
    body: str,
    workspace: str | None = None,
    ax_id: str | None = None,
) -> None:
    """Handle a notification from the macOS watcher daemon.

    Args:
        app_bundle_id: The bundle ID of the app that posted the notification
        title: The notification title (often sender/channel name)
        body: The notification body (message preview)
        workspace: Workspace name (for Slack multi-workspace)
        ax_id: macOS accessibility identifier for deduplication
    """
    if app_bundle_id != SLACK_BUNDLE_ID:
        return

    # Slack integration requires configuration - skip if not set up
    slack_config = _get_slack_config()
    if not slack_config:
        return

    # Check blocklist - title is the channel/DM name
    if slack_config.is_blocked(title):
        return

    with db.connect() as conn:
        # Check if we've already seen this notification and user marked it read
        if ax_id and _is_already_seen_and_read(conn, ax_id):
            return

        # For Slack, title is usually the channel/DM name, body is the message
        safe_title = title[:32].replace(":", "-").replace("/", "-") if title else "unknown"
        channel = f"slack:{safe_title}"
        name = title if title else "slack"
        message = body if body else "New message"

        metadata = {
            "app_bundle_id": app_bundle_id,
            "title": title,
            "body": body,
        }
        if workspace:
            metadata["workspace"] = workspace
        if ax_id:
            metadata["ax_id"] = ax_id

        db.add(
            conn,
            channel=channel,
            message=message,
            name=name,
            metadata=metadata,
            switch_source="slack",
        )
