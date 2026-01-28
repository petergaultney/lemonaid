# macOS Notification Center Integration

Lemonaid can capture notifications from macOS Notification Center and add them to your inbox. This is useful for monitoring Slack messages (and potentially other apps) without keeping those apps in focus.

## Requirements

- macOS (tested on macOS 14+)
- Accessibility permissions (for reading Notification Center)
- PyObjC dependencies

## Setup

### 1. Install dependencies

```bash
# With uv (recommended):
uv pip install lemonaid[macos]

# Or with pip:
pip install lemonaid[macos]
```

If using `uv tool install`:
```bash
uv tool install --editable path/to/lemonaid \
  --with pyobjc-framework-Quartz \
  --with pyobjc-framework-ApplicationServices
```

The `macos` extra provides the notification watcher daemon.

### 2. Install and start the watcher daemon

```bash
lemonaid macos install-watcher
```

This:
1. Creates a LaunchAgent plist at `~/Library/LaunchAgents/com.lemonaid.notification-watcher.plist`
2. Starts the watcher daemon
3. Prompts for Accessibility permissions if needed

### 3. Grant Accessibility permissions

The watcher needs Accessibility permissions to read Notification Center. macOS should prompt you automatically, but if not:

1. Open System Settings > Privacy & Security > Accessibility
2. Click the '+' button
3. Navigate to your Python executable (shown in the install output)
4. Ensure the checkbox is enabled

To open System Settings directly:
```bash
open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'
```

Verify permissions are working:
```bash
lemonaid macos logs -f
```

You should see "Watcher started. Listening for notifications..."

## How it works

1. A LaunchAgent daemon watches macOS Notification Center using the Accessibility API
2. When a notification appears, the daemon extracts app name, title, subtitle, and body
3. The daemon calls `lemonaid macos notify` with the notification details
4. Lemonaid filters (currently Slack only) and adds matching notifications to the inbox

### Deduplication

Each macOS notification has a unique accessibility ID (`ax_id`). When you mark a notification as read in lemonaid, that `ax_id` is recorded. If macOS re-fires the same notification (e.g., when Notification Center refreshes), lemonaid skips it.

## CLI commands

```bash
# Install watcher daemon
lemonaid macos install-watcher

# Uninstall watcher daemon
lemonaid macos uninstall-watcher

# Check watcher status
lemonaid macos status

# View watcher logs
lemonaid macos logs
lemonaid macos logs -f          # follow (like tail -f)
lemonaid macos logs -n 50       # show 50 lines

# Handle notification (called by daemon, not typically used directly)
lemonaid macos notify --app <bundle_id> --title "..." --body "..." --ax-id "..."
```

## Slack Integration

Slack integration is **opt-in** - without configuration, Slack notifications are silently ignored.

### Quick setup

1. **Enable Slack integration** by adding to `~/.config/lemonaid/config.toml`:
   ```toml
   [slack]
   # That's it! Just having this section enables Slack integration.

   # Optional: block specific channels/DMs from appearing in inbox
   blocklist = [
     "#announcements",
     "#social-general",
     "Slackbot",
   ]
   ```

2. **Generate channel ID mappings** (see below)

### Generating mappings

Lemonaid needs channel/user IDs to construct `slack://` deep links. Unfortunately, Slack doesn't make this easy - you need to export the data from the browser.

**For each workspace:**

1. Open Slack in a web browser (not the desktop app)
2. Open DevTools (F12) → **Application** → **IndexedDB**
3. Expand **reduxPersistence** → **reduxPersistenceStore**
4. Find the row with key like `persist:slack-client-...`
5. Click on it, then right-click the **Value** preview and select "Copy object"
6. Save to a file (e.g., `slack-export.json`)

Then extract the mappings with jq:

```bash
# Get team ID (starts with T)
TEAM_ID=$(jq -r '.teams | keys[] | select(startswith("T"))' slack-export.json)

# Get workspace name for the JSON key
WORKSPACE_NAME="My Workspace"  # Use the actual name shown in Slack

# Extract channels and DMs, build mappings file
jq -n \
  --arg ws "$WORKSPACE_NAME" \
  --arg team "$TEAM_ID" \
  --slurpfile data slack-export.json '
{
  ($ws): {
    "team_id": $team,
    "channels": ([$data[0].channels | to_entries[] | select(.value.is_channel == true) | {key: ("#" + .value.name), value: .key}] | from_entries),
    "dms": ([$data[0].channels | to_entries[] | select(.value.is_im == true) | {key: ($data[0].members[.value.user].real_name // .value.user), value: .key}] | from_entries)
  }
}' > /tmp/slack-workspace.json

# For first workspace, or to overwrite:
mv /tmp/slack-workspace.json ~/.local/state/lemonaid/slack-mappings.json

# For additional workspaces, merge into existing file:
jq -s '.[0] * .[1]' ~/.local/state/lemonaid/slack-mappings.json /tmp/slack-workspace.json > /tmp/merged.json \
  && mv /tmp/merged.json ~/.local/state/lemonaid/slack-mappings.json
```

**Multiple workspaces:** Repeat the browser export and jq extraction for each workspace, using the merge command to combine them.

### How it works

1. macOS watcher captures Slack notifications (workspace name, channel, message)
2. When you select a notification, lemonaid looks up the channel ID in cached mappings
3. Opens `slack://channel?team=...&id=...` to go directly to the conversation
4. If lookup fails, falls back to just opening Slack

### Viewing mappings

```bash
lemonaid slack show-mappings              # show all
lemonaid slack show-mappings -w "My Team" # show specific workspace
lemonaid slack path                       # show mappings file path
```

Mappings are stored in `~/.local/state/lemonaid/slack-mappings.json`.

### Disabling Slack integration

Remove or comment out the `[slack]` section in your config. Slack notifications will be ignored until re-enabled.

## Log locations

- stdout: `~/.local/state/lemonaid/logs/watcher.log`
- stderr: `~/.local/state/lemonaid/logs/watcher.err`

## Troubleshooting

### Watcher not starting

```bash
# Check status
lemonaid macos status

# View error log
cat ~/.local/state/lemonaid/logs/watcher.err
```

### "Accessibility permission not granted"

1. Open System Settings > Privacy & Security > Accessibility
2. Add the Python executable shown in the error log
3. Restart the watcher:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.lemonaid.notification-watcher.plist
   launchctl load ~/Library/LaunchAgents/com.lemonaid.notification-watcher.plist
   ```

### Notifications not appearing in inbox

1. **Check watcher logs**: `lemonaid macos logs -f`
2. **Verify it's Slack**: Only Slack notifications are currently captured
3. **Check for "No notification banners found"**: The watcher filters out widgets (Weather, Calendar, etc.)

### Same notification keeps appearing

This shouldn't happen if deduplication is working. Check:
```bash
# See ax_id in notification metadata
sqlite3 ~/.local/share/lemonaid/lemonaid.db \
  "SELECT id, channel, status, json_extract(metadata, '$.ax_id') FROM notifications WHERE channel LIKE 'slack:%'"
```

## Architecture

The design separates concerns:

- **Watcher daemon** (`watcher.py`): "Dumb" - just watches Notification Center and calls `lemonaid macos notify`. Rarely needs updates.
- **Notification handler** (`notify.py`): "Smart" - filters apps, deduplicates, adds to inbox. All logic lives here.
- **LaunchAgent** (`launchd.py`): Manages daemon lifecycle via macOS launchctl.

This means the daemon can stay running even as you update lemonaid - the smart logic is in the CLI command it calls.
