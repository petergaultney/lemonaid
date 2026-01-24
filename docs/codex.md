# Codex CLI Integration

Lemonaid integrates with [OpenAI Codex CLI](https://github.com/openai/codex) to receive notifications when Codex completes a turn or needs approval.

## Setup

### 1. Configure Codex to notify lemonaid

Add to `~/.codex/config.toml` **at the very top** (before any `[table]` headers):

```toml
# Must be at root level (before any [table] headers)
notify = ["lemonaid", "codex", "notify"]

[projects."/path/to/project"]
# ... rest of your config
```

**Important**: In TOML, anything after a `[table]` header belongs to that table. The `notify` setting must appear before any tables to be recognized as a root-level setting.

### 2. Configure lemonaid handler (optional)

In `~/.config/lemonaid/config.toml`:

```toml
[handlers]
"codex:*" = "tmux"  # or "wezterm"
```

If not configured, Codex notifications will still appear in the inbox but won't auto-switch to the pane.

## How it works

### Notification flow

1. Codex completes a turn (or requests approval)
2. Codex calls `lemonaid codex notify '<json>'` with event data
3. Lemonaid extracts session ID, cwd, and notification type
4. Notification appears in `lma` inbox with channel `codex:<session_id_prefix>`

### Auto-dismiss

The Codex watcher monitors `~/.codex/sessions/*.jsonl` files for activity. When Codex starts working again (function calls, web searches, assistant messages), the notification is automatically marked as read.

### Live activity updates

While Codex is working, the notification message updates to show current activity:

- "Running ls" (shell commands)
- "Reading /path/to/file" (MCP resources)
- "Searching: query" (web searches)
- First line of assistant responses

## CLI commands

```bash
# Manually trigger a notification (for testing)
lemonaid codex notify '{"type": "agent-turn-complete", "thread-id": "abc123", "cwd": "/path/to/project"}'

# Dismiss a session's notification
lemonaid codex dismiss --session-id abc123
```

## JSON payload format

Codex passes a JSON argument with these fields:

| Field | Description |
|-------|-------------|
| `type` | Event type: `agent-turn-complete`, `approval-requested` |
| `thread-id` | Session/thread identifier |
| `cwd` | Working directory |
| `input-messages` | User messages that triggered the turn |
| `last-assistant-message` | Final assistant response text |

Lemonaid also checks for alternative key names (`session_id`, `sessionId`, `thread_id`, etc.) for compatibility.

## Session files

Codex stores sessions in `~/.codex/sessions/` as JSONL files:

```
~/.codex/sessions/rollout-2026-01-23T23-32-37-<uuid>.jsonl
```

Each line is a JSON entry with `type` and `payload` fields. The watcher reads these to detect activity and extract status updates.

## Troubleshooting

### Notifications not appearing

1. **Check config placement**: The `notify` line must be at the top of `~/.codex/config.toml`, before any `[table]` headers

2. **Test manually**:
   ```bash
   lemonaid codex notify '{"type": "agent-turn-complete", "thread-id": "test-12345678", "cwd": "/tmp"}'
   lemonaid inbox list
   ```

3. **Check logs**:
   ```bash
   cat /tmp/lemonaid-codex-notify.log
   ```

### Notifications not auto-dismissing

1. **Check watcher logs**:
   ```bash
   cat /tmp/lemonaid-codex-watcher.log
   ```

2. **Verify session file exists**:
   ```bash
   ls -la ~/.codex/sessions/*.jsonl
   ```

3. **Check notification metadata** has `session_id` and `cwd`:
   ```bash
   lemonaid inbox list --json | jq '.[] | select(.channel | startswith("codex:"))'
   ```

### Switching to pane doesn't work

1. **Check handler config**: Make sure `"codex:*"` is mapped in `~/.config/lemonaid/config.toml`

2. **Verify TTY metadata**: The notification needs a `tty` in metadata for pane switching to work
