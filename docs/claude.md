# Claude Code Integration

Lemonaid integrates with [Claude Code](https://claude.ai/claude-code) to receive notifications when Claude finishes responding or needs permission.

## Setup

### 1. Add hooks to Claude settings

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "lemonaid claude submit"
          }
        ]
      }
    ],
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
    "PermissionRequest": [
      {
        "matcher": "AskUserQuestion",
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
- **UserPromptSubmit hook**: Registers the session in the inbox the moment you submit a prompt, as a read/working entry (not flagged for attention). This is what makes a session appear while it's still working, rather than only once it stops.
- **Stop hook**: Notification when Claude finishes responding and is waiting for input
- **PermissionRequest hook**: Notification when Claude asks a question mid-turn via the `AskUserQuestion` tool (the interactive picker). Without this, questions go unnoticed if you've tabbed away - `Stop` doesn't fire because Claude hasn't finished its turn.
- **Notification hook**: Notification when Claude needs tool permission

A session enters the inbox only when a hook fires. Without the `UserPromptSubmit` hook, a session is invisible until its first `Stop` or permission prompt - so a long-running turn (especially in auto-accept mode, where permission prompts never fire) won't show up until it pauses.

## How it works

### Notification flow

1. You submit a prompt -> Claude Code runs `lemonaid claude submit`, which registers the session as read/working (it appears in the inbox immediately, without being flagged for attention)
2. Claude finishes a response (or needs permission) -> Claude Code runs `lemonaid claude notify` with session data via stdin
3. Lemonaid extracts session ID, cwd, and notification type, and flips the session to unread (needs attention)
4. The notification appears in `lma` inbox with channel `claude:<session_id_prefix>`

The working registration never reorders or re-flags an existing session: a session you're actively driving holds a stable position, and `created_at` (its birth time) is never overwritten. A prompt to an archived session brings it back as a working entry.

### Auto-dismiss via transcript watching

Lemonaid monitors Claude transcript files in `~/.claude/projects/<encoded-cwd>/<session_id>.jsonl` to detect when you provide input. For git worktrees, it also checks parent directories to find the matching Claude project path. When Claude starts working (thinking, running tools), the notification is dismissed automatically.

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

## Custom statusline (optional)

Lemonaid provides an optional statusline command that shows:

- Current time with elapsed time since last message (in red)
- Working directory basename (in blue)
- Git branch (in cyan)
- Context window usage percentage (color gradient: indigo → blue → green → yellow → red → magenta)
- Vim mode indicator `[N]`/`[I]`

Example output: `<14:32:15 3.2s> lemonaid feature/new-thing 23%`

### Setup

Add to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "lemonaid-claude-statusline"
  },
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "lemonaid-claude-statusline write-last-message-time"
          }
        ]
      }
    ]
  }
}
```

The `UserPromptSubmit` hook records when you send a message, enabling the elapsed time display. Without this hook, elapsed time won't be shown but everything else still works.

If you also use the `lemonaid claude submit` working-registration hook (above), both commands go in the same `UserPromptSubmit` array as separate entries — they both fire on each submit.

## Faster notifications

Claude Code has a hardcoded 6-second polling interval for notification hooks, causing ~10 second delays. Lemonaid can patch the binary to reduce this to 500ms.

See [claude-patch.md](claude-patch.md) for details.

## Session naming

Claude names a conversation itself once it has some content, writing the name
into the session transcript as `type: "ai-title"` entries (field `aiTitle`). A
`/rename` is recorded the same way as `customTitle`. Lemonaid reads the
transcript and prefers, in order:

1. `customTitle` — your own `/rename`
2. `aiTitle` — Claude's generated conversation title
3. A `summary` or `firstPrompt` from `sessions-index.json`, for older sessions
4. The tmux session name, or the working directory name

None of the first three exist when a session starts, so a new session shows a
tmux/cwd placeholder and is renamed in place once Claude assigns a title. The TUI
re-checks unnamed sessions periodically (on a background thread), so a
long-running session picks up its real name without needing another hook to fire.

A name you set yourself always wins and is never overwritten. Clearing a rename
(`r`, then empty) restores the latest title Claude has assigned, not the original
placeholder.

Note on `sessions-index.json`: current Claude versions no longer maintain this
file, so it only covers sessions from before that change. It remains the source
for `lemonaid claude bootstrap`, which imports historical sessions.

## Session files

Claude stores session data in `~/.claude/projects/<encoded_dir>/`:

```
~/.claude/projects/-Users-peter-play-lemonaid/
  sessions-index.json    # Legacy session index (no longer written by current versions)
  <session_id>.jsonl     # Full conversation history, including ai-title entries
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
   rg 'lemonaid\\.claude' /tmp/lemonaid.log
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
   rg 'lemonaid\\.(watcher|claude)' /tmp/lemonaid.log
   ```

2. **Verify transcript file exists**:
   ```bash
   ls ~/.claude/projects/*/*.jsonl
   ```

3. **Check notification metadata** has `session_id` and `cwd`:
   ```bash
   lemonaid inbox list --json | jq '.[] | select(.channel | startswith("claude:"))'
   ```
