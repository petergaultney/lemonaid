# Claude Code Integration

Lemonaid integrates with [Claude Code](https://claude.ai/claude-code) to receive notifications when Claude finishes responding or needs permission.

## Setup

### 1. Add hooks to Claude settings

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "lemonaid claude notify"
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "permission_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "lemonaid claude notify"
          }
        ]
      }
    ]
  }
}
```

This gives you:
- **Stop hook**: Notification when Claude finishes responding and is waiting for input
- **Notification hook**: Notification when Claude needs permission

### 2. Configure lemonaid handler

In `~/.config/lemonaid/config.toml`:

```toml
[handlers]
"claude:*" = "tmux"  # or "wezterm"
```

## How it works

### Notification flow

1. Claude finishes a response (or needs permission)
2. Claude Code runs `lemonaid claude notify` with session data via stdin
3. Lemonaid extracts session ID, cwd, and notification type
4. Notification appears in `lma` inbox with channel `claude:<session_id_prefix>`

### Auto-dismiss via transcript watching

Lemonaid monitors Claude's transcript files (`~/.claude/projects/<dir>/transcript.jsonl`) to detect when you provide input. When Claude starts working (thinking, running tools), the notification is dismissed automatically.

This is more reliable than hook-based dismiss because:
- No race conditions with the Stop hook
- Works for all input types (prompts, permission grants, etc.)
- No additional hooks needed (reduces overhead)

The transcript watcher starts automatically when the TUI runs.

### Live activity updates

While Claude is working, the notification message updates to show current activity:

- "Reading file.py" (Read tool)
- "Running pytest" (Bash tool)
- "Searching for pattern" (Grep tool)
- "Editing config.toml" (Edit tool)

## CLI commands

```bash
# Handle notification from hook (reads JSON from stdin)
lemonaid claude notify

# Dismiss current session's notification
lemonaid claude dismiss

# Binary patching for faster notifications
lemonaid claude patch-status
lemonaid claude patch
lemonaid claude patch-restore
```

## Faster notifications

Claude Code has a hardcoded 6-second polling interval for notification hooks, causing ~10 second delays. Lemonaid can patch the binary to reduce this to 500ms.

See [claude-patch.md](claude-patch.md) for details.

## Session naming

Claude Code sessions can be named with `/rename`. This name appears in the lemonaid inbox. If unnamed, lemonaid derives a name from:

1. The session name from `sessions-index.json`
2. The first user message (truncated)
3. The working directory name

## Session files

Claude stores session data in `~/.claude/projects/<encoded_dir>/`:

```
~/.claude/projects/-Users-peter-play-lemonaid/
  sessions-index.json    # Maps session IDs to names
  sessions/
    <session_id>/
      transcript.jsonl   # Full conversation history
```

The transcript watcher reads these to detect activity and extract tool usage.

## Troubleshooting

### Notifications not appearing

1. **Check hooks are configured**:
   ```bash
   cat ~/.claude/settings.json | jq '.hooks'
   ```

2. **Test manually** (you can't easily test the hook, but check logs):
   ```bash
   cat /tmp/lemonaid-claude-notify.log
   ```

3. **Verify Claude Code is using hooks**: Look for hook execution messages in Claude's output

### Notifications delayed by ~10 seconds

Claude Code has a 6-second polling interval. Apply the binary patch:

```bash
lemonaid claude patch
```

See [claude-patch.md](claude-patch.md) for details.

### Notifications not auto-dismissing

1. **Check watcher logs**:
   ```bash
   cat /tmp/lemonaid-claude-watcher.log
   ```

2. **Verify transcript file exists**:
   ```bash
   ls ~/.claude/projects/*/sessions/*/transcript.jsonl
   ```

3. **Check notification metadata** has `session_id` and `cwd`:
   ```bash
   lemonaid inbox list --json | jq '.[] | select(.channel | startswith("claude:"))'
   ```
