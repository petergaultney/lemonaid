# OpenCode Integration

Lemonaid supports [OpenCode](https://opencode.ai/) sessions via plugin events and session DB watching.

## How It Works

1. OpenCode plugin emits events to `lemonaid opencode notify` when a session goes idle or asks permission
2. Lemonaid stores notification metadata (`cwd`, `session_id`, `tty`, `switch_source`) in the inbox DB
3. The unified watcher reads OpenCode session activity from `~/.local/share/opencode/opencode.db`
4. When OpenCode resumes work (user/assistant activity, tool calls), the notification auto-marks as read
5. When OpenCode completes a turn (`step-finish` with `reason: "stop"`), the watcher marks the session unread again

## Setup

### 1) Ensure lemonaid has OpenCode commands

```bash
lemonaid opencode --help
```

If this fails, reinstall your local editable tool:

```bash
cd ~/play/lemonaid
uv tool install --editable . --reinstall
```

### 2) Add OpenCode plugin

Create `~/.config/opencode/plugins/lemonaid.js` (global) or `.opencode/plugins/lemonaid.js` (project):

```javascript
export const LemonaidPlugin = async ({ $ }) => ({
  event: async ({ event }) => {
    if (event.type === "session.idle" || event.type === "permission.asked") {
      await $`lemonaid opencode notify ${JSON.stringify(event)}`
    }
  },
})
```

Restart OpenCode after adding the plugin.

### 3) Verify notifications are flowing

```bash
# synthetic event (smoke test)
lemonaid opencode notify '{"type":"session.idle","properties":{"sessionID":"ses_test123"}}'

# verify in inbox
lemonaid inbox list --json
```

### 4) Troubleshooting

- Ensure plugin path is exactly `~/.config/opencode/plugins/lemonaid.js`
- Fully restart OpenCode after plugin changes
- Check logs: `rg 'lemonaid\.opencode|opencode\.notify|watcher' /tmp/lemonaid.log`

## CLI Commands

```bash
# Manually trigger a notification
lemonaid opencode notify '{"type":"session.idle","properties":{"sessionID":"ses_abc123"}}'

# Mark a session notification as read
lemonaid opencode dismiss --session-id ses_abc123
```

## Session Storage

- OpenCode DB: `~/.local/share/opencode/opencode.db`
- Session table: `session`
- Activity stream used by watcher: `message` + `part`

## Technical Notes

- Channel format: `opencode:<full_session_id>`
- Resume command from history: `opencode --session <session_id>`
- Notifications include terminal metadata when available for tmux/wezterm switching
