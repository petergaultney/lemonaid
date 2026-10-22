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

### 2. Report permission prompts (optional)

Codex's `notify` reports only finished turns. To have the inbox show a Codex lemon as
`blocked` while it waits on an approval, add a `PermissionRequest` hook to
`~/.codex/hooks.json`:

```json
{
  "hooks": {
    "PermissionRequest": [
      { "hooks": [{ "type": "command", "command": "lemonaid codex notify" }] }
    ]
  }
}
```

Codex asks you to trust a new hook the first time it loads it.

`PermissionRequest` also runs for requests handled by Codex's automatic approval
reviewer. Lemonaid checks the requesting turn's `approvals_reviewer` in its rollout
and ignores shell and patch hooks when it is `auto_review`, so these reviews do not show
"Permission needed" or surface hidden lemons. User-reviewed requests still appear
immediately. If the turn's reviewer cannot be determined, the request appears as a
permission notice. MCP/app requests stay visible because an app can override the
turn's reviewer. This uses the running turn's context rather than global config,
which can differ from a session's effective settings.

`lemonaid hooks install --harness codex` adds lemonaid's lemon-side hooks to the same file,
beside yours: PreToolUse and PostToolUse hooks that keep a lemon's own edits and pushes from
waking its watchers, the `lemonaid codex tool-used` PreToolUse and PostToolUse hooks
(section 3 below), a Stop hook that requires the unified watcher for subscribed briefs
and a valid brief, and a SessionStart hook. The SessionStart and Stop hooks start the
lemon's push scout (below). Codex
trusts each hook by a hash of it (`[hooks.state]` in `config.toml`), so after installing, or
after an upgrade changes a hook, trust them again in Codex's `/hooks`.

Stop checks resolve an attached transient notification channel from verified terminal
ownership even before the first turn-complete notification records its root thread.
Codex treats a blocking Stop response as a request to continue the turn.

A Codex lemon with a brief gets a push scout: a detached `lemonaid watch --self --push`
that queues each batch of watch events and messages into its thread with `codex queue`
and keeps watching, so the lemon never rearms a watcher. It runs outside the Codex
sandbox, since `codex queue` writes `~/.codex`, and exits when no Codex process has the
thread's rollout open or the brief is detached. The SessionStart and Stop hooks start it. The
inbox also starts one at startup and every ten seconds for a live, idle Codex lemon with
a brief and no watcher, at most once a minute per lemon. It uses the persistent
root thread for delivery and preserves the attached brief's channel, and skips dead,
unknown, archived, mid-turn and pending-handoff sessions. A lemon whose
`lemonaid watch --self --status` says `no watcher running` can start its own with
`lemonaid watch --self --push`, run with escalated permissions. See
[watch.md](watch.md#the-push-scout).

Codex 0.163's automatic recaps run in temporary threads that send ordinary
turn-complete notifications but never save a rollout. Lemonaid logs and ignores
any notification whose thread has no rollout before opening the inbox database,
so recap rows never appear and recaps do not change the lemon's unread state.
UUIDv7 thread IDs give the creation date; lookup checks that date's directory
under `~/.codex/sessions/` and the adjacent days. Notifications with a thread ID
never fall back to another conversation in the same directory. Rollouts with a
`parent_thread_id` are also ignored.

Notification identity does not depend on a terminal or multiplexer. Existing
unattached duplicates are cleaned up at startup and during refresh, preserving
brief attachments and waiter channels.

### 3. Allow brief and message commands under the automatic approval reviewer

With `approvals_reviewer = "auto_review"` in `~/.codex/config.toml`, Codex can reject these commands because they write outside the project workspace. Add these rules to `~/.codex/rules/default.rules` if Codex lemons use briefs and lemon-to-lemon messages:

```text
prefix_rule(pattern=["lemonaid", "brief"], decision="allow")
prefix_rule(pattern=["lemonaid", "tell"], decision="allow")
prefix_rule(pattern=["lemonaid", "inbox", "watch"], decision="allow")
prefix_rule(pattern=["lemonaid", "inbox", "next"], decision="allow")
prefix_rule(pattern=["lemonaid", "watch"], decision="allow")
```

These commands write under `~/.lemons/` (`~/.brief-lemons/` before `lemonaid home migrate`) and `~/.local/share/lemonaid/`, outside the project workspace. An `allow` rule lets a matching command run outside the sandbox without prompting. Codex matches rules only against commands it can split into plain words, so a command with a shell expansion in it (`--codex-thread "$CODEX_THREAD_ID"`) goes to the approval reviewer instead; write `--codex-thread` bare. Restart running Codex sessions after changing `default.rules`, since they read the rules at session start.

### 3. Clear permission notices after approval

Add `PreToolUse` and `PostToolUse` handlers to `~/.codex/hooks.json` so a permission notice clears when its requested tool starts, with `PostToolUse` as a fallback when the tool returns:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "lemonaid codex tool-used"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "lemonaid codex tool-used"
          }
        ]
      }
    ]
  }
}
```

`lemonaid hooks install --harness codex` adds these entries beside your other hooks and only if they aren't there already; `--uninstall` removes them. Codex requires you to trust the new `PreToolUse` hook in `/hooks`. To add the entries by hand, merge them into the existing `hooks` object and keep any other hooks already configured. Lemonaid clears only a matching `PermissionRequest` from the same Codex session, turn, and tool. The `PreToolUse` hook clears it when the approved tool starts; `PostToolUse` handles cases where the tool returns without a matching start event, including nonzero command exits. A request that remains unanswered stays unread and visible.

## How it works

### Notification flow

1. Codex completes a turn (or requests approval)
2. Codex calls `lemonaid codex notify '<json>'` with event data
3. Lemonaid extracts session ID, cwd, and notification type
4. Notification appears in `lma` inbox with channel `codex:<thread_id>`

### Auto-dismiss

The Codex watcher monitors JSONL session files under `~/.codex/sessions/` for activity. When Codex starts working again (function calls, web searches, assistant messages), the notification is automatically marked as read. The hooks above also clear a matching permission notice when its approved tool starts or returns.

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

`lemonaid codex tool-used` is called by the `PreToolUse` and `PostToolUse` hooks with
Codex's event JSON on stdin.

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
   rg 'lemonaid\\.codex' /tmp/lemonaid.log
   ```

### Notifications not auto-dismissing

1. **Check watcher logs**:
   ```bash
   rg 'lemonaid\\.(watcher|codex)' /tmp/lemonaid.log
   ```

2. **Verify session file exists**:
   ```bash
   find ~/.codex/sessions -name '*.jsonl' -maxdepth 5
   ```

3. **Check notification metadata** has `session_id` and `cwd`:
   ```bash
   lemonaid inbox list --json | jq '.[] | select(.channel | startswith("codex:"))'
   ```

### Switching to pane doesn't work

1. **Check switch-source**: Codex pane switching is auto-selected from notification `switch_source` (`tmux`/`wezterm`/`cmux`), no `[handlers]` mapping required

2. **Verify TTY metadata**: The notification needs a `tty` in metadata for pane switching to work

   A session run by Codex's shared `codex app-server` daemon records no `tty`: the daemon holds the tty of the TUI that started it, not this session's. Switching then finds the pane by the session's `cwd`, and the watcher archives the row once no `codex` process other than the daemon is working in that directory.

   That can't tell two Codex sessions in one directory apart: when one ends, its row stays until the other does too. To avoid the daemon altogether, set `daemon_auto_start = false` under `[features]` in `~/.codex/config.toml`:

   ```toml
   [features]
   daemon_auto_start = false
   ```

   That stops every Codex launch from starting or joining the daemon, including a bare `codex` in a window, a respawn, and a resume. `codex --no-daemon` does the same for one launch, so it only helps for launches through lemonaid's templates. Its hooks then run in its own pane and record that pane's `tty`, like Claude's. `lemonaid tmux doctor` warns when the setting is missing.
