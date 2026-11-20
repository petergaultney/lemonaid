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
reviewer. Lemonaid checks the requesting turn's `approvals_reviewer` in the thread's
rollout file, at the path Codex reports for the thread, since Codex reports the reviewer
nowhere else. It ignores shell and patch hooks when it is `auto_review`, so these reviews do not show
"Permission needed" or surface hidden lemons. User-reviewed requests still appear
immediately. If the turn's reviewer cannot be determined, the request appears as a
permission notice. MCP/app requests stay visible because an app can override the
turn's reviewer. This uses the running turn's context rather than global config,
which can differ from a session's effective settings.

`lemonaid hooks install --harness codex` adds lemonaid's lemon-side hooks to the same file,
beside yours: PreToolUse and PostToolUse hooks that keep a lemon's own edits and pushes from
waking its watchers, the `lemonaid codex turn` hook (section 4 below), a Stop hook that requires the unified watcher for subscribed briefs
and a valid brief, a SessionStart hook, and a SessionEnd hook that records a quit, so a
thread that stops without one is kept to restore (see [tmux](tmux.md#telling-a-quit-from-a-crash)).
The SessionStart hook also gives a new
thread its inbox row, with its pane, so a brief waiting on its window (`place open
--brief`, `lemon start --brief`) is attached as it starts rather than when its first turn
ends. The SessionStart and Stop hooks start the lemon's push scout (below). Each hook is
named in `/hooks` (`lemonaid: session-start`, for instance) by its `statusMessage`, which
Codex also shows while a slow hook runs. Codex
trusts each hook by a hash of it (`[hooks.state]` in `config.toml`), so after installing, or
after an upgrade changes a hook, trust them again in Codex's `/hooks`.

Codex treats a blocking Stop response as a request to continue the turn.

A Codex lemon with a brief gets a push scout: `lemonaid watch --self --push` registers it
with the scout host, which runs every lemon's scout and queues each batch of watch events and messages into its thread with `codex queue`
and keeps watching, so the lemon never rearms a watcher. It runs outside the Codex
sandbox, since `codex queue` writes `~/.codex`, and exits when no Codex process runs the
thread or the brief is detached. The SessionStart and Stop hooks start it. The
inbox also starts one at startup and every ten seconds for a live, idle Codex lemon with
a brief and no watcher, at most once a minute per lemon. It skips dead, unknown,
archived, mid-turn and pending-handoff sessions. A lemon whose
`lemonaid watch --self --status` says `no watcher running` can start its own with
`lemonaid watch --self --push`, run with escalated permissions. See
[watch.md](watch.md#the-push-scout).

Codex 0.163's automatic recaps run in temporary threads that send ordinary
turn-complete notifications but are never stored. Lemonaid asks Codex about each
notification's thread (see [What lemonaid asks Codex](#what-lemonaid-asks-codex)) and logs
and ignores one Codex doesn't know before opening the inbox database, so recap rows never
appear and recaps do not change the lemon's unread state. Notifications with a thread ID
never fall back to another conversation in the same directory. Threads Codex records with a
parent (subagents and approval reviewers) are also ignored.

### 3. Allow brief and message commands under the automatic approval reviewer

With `approvals_reviewer = "auto_review"` in `~/.codex/config.toml`, Codex can reject these commands because they write outside the project workspace. Add these rules to `~/.codex/rules/default.rules` if Codex lemons use briefs and lemon-to-lemon messages:

```text
prefix_rule(pattern=["lemonaid", "brief"], decision="allow")
prefix_rule(pattern=["lemonaid", "tell"], decision="allow")
prefix_rule(pattern=["lemonaid", "mailbox", "watch"], decision="allow")
prefix_rule(pattern=["lemonaid", "mailbox", "next"], decision="allow")
prefix_rule(pattern=["lemonaid", "watch"], decision="allow")
```

These commands write under `~/.lemons/` (`~/.brief-lemons/` before `lemonaid home migrate`) and `~/.local/share/lemonaid/`, outside the project workspace. An `allow` rule lets a matching command run outside the sandbox without prompting. Codex matches rules only against commands it can split into plain words, so a command with a shell expansion in it (`--codex-thread "$CODEX_THREAD_ID"`) goes to the approval reviewer instead; write `--codex-thread` bare. Restart running Codex sessions after changing `default.rules`, since they read the rules at session start.

### 4. Record turns and activity

`lemonaid codex turn` runs on Codex's `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
`Interrupt` and `PostModelRequest` hooks, without Codex waiting for it. It records when a
turn starts (and marks the row read, since its user is back), what the lemon is doing, an
interrupt, the model and the context used, and clears a permission notice when its requested
tool starts or returns. The notify hook's turn-complete records the turn's end.

`lemonaid hooks install --harness codex` adds these entries beside your other hooks and only
if they aren't there already, replacing the `lemonaid codex tool-used` hooks of earlier
versions; `--uninstall` removes them. Trust the new hooks in Codex's `/hooks`. Lemonaid clears
only a matching `PermissionRequest` from the same Codex session, turn, and tool. A request
that remains unanswered stays unread and visible.

## How it works

### Notification flow

1. Codex completes a turn (or requests approval)
2. Codex calls `lemonaid codex notify '<json>'` with event data
3. Lemonaid extracts session ID, cwd, and notification type
4. Notification appears in `lma` inbox with channel `codex:<thread_id>`

### Turns and activity

The turn hook (section 4) keeps the row current. A prompt marks it read and shows
"Working...", and each tool the lemon starts shows what it is doing: "Running: uv run pytest"
for a shell command, "Editing src/a.py" for a patch, "Using create_issue" for an app. The
context column shows the tokens the last model request sent; Codex reports no window size,
so a Codex lemon shows its window only when an earlier version recorded one.

The turn hook runs asynchronously, so its reports can arrive out of order; the
[decision record](decisions/codex-turn-hooks-run-async.md) says how lemonaid handles that
and why the hooks aren't synchronous.

### What lemonaid asks Codex

lemonaid reads none of Codex's own files to learn about threads. The scout host keeps one
private `codex app-server` on stdio (never Codex's shared daemon) and writes what Codex has
stored about every thread lemonaid has asked about to
`~/.local/state/lemonaid/codex/threads.json`: whether it exists or is archived, its directory,
title, parent and rollout path. It re-reads them each minute, and sooner for a thread it
hasn't read. Hooks, the inbox and commands read that file. A thread not in it yet is asked
of a short-lived app-server, which also starts the scout host. With no Codex to ask, a thread
counts as unknown, never as gone. The handoff ready marker and typed phrases come from
`thread/turns/list`, hook trust from `hooks/list`, and rate limits from
`account/rateLimits/read`.

Which Codex process runs which thread comes from what Codex's hooks recorded: each hook
records the process it runs under, and one still running (the same pid, started at the same
moment) runs the thread it reported last. A process restore resumed that hasn't run a hook
yet runs the thread its `resume` argument names.

### Messages Codex holds

The push scout and the delivery service give each message to Codex with `codex queue`.
Codex writes it to its own queue and exits 0, whether or not a process will run it. A
Codex process that has the thread loaded starts a turn from it when the thread is idle.
After an Esc interrupt, it starts none until its user's next prompt.

lemonaid queries Codex's queue, `queue_1.sqlite` in the Codex home, through a
short-lived SQLite read-only connection. It reads committed messages directly from the
live database and WAL, without copying them or changing queue rows. SQLite may create or
update its WAL sidecars for normal reader coordination. A locked database is given up to
one second to become readable; other read failures also skip detection for that check
and log a warning with the path and error in `/tmp/lemonaid.log` (or `LEMONAID_LOG`).
Missing tables or columns after a Codex schema change are logged this way too. When a
message has waited 60 seconds on an idle thread that a Codex process has open, the lemon
is `parked`. `tell` exits 1 and says why, `lma` marks it `deaf`, and its parent wakes
once. Codex's hooks say whether the thread is idle, and whether an Esc ended its last turn.
A healthy thread starts a queued message within about 10 seconds of being idle, so 60
seconds gives no false report for a lemon that is mid-turn or has just finished a turn.
lemonaid types nothing into a parked lemon's pane: after an Esc, a prompt there would undo
its user's interrupt. Codex keeps the messages, and runs them after the next prompt.

A thread that no Codex process runs is not `parked`: no process runs it, so it is
`dead`, and a resume runs what Codex holds for it.

lemonaid can't see these cases:

- **A thread switch in the pane** (`/new`, `/resume`, `/fork`). Codex keeps the old thread
  loaded for 60 seconds, and runs its queued messages where no one sees them. Then it
  unloads the thread. The scout stops when no process runs the thread, and `tell`
  treats the lemon as `dead`.
- **Codex's daemon** (a launch without `--no-daemon`). The Left Arrow agents view and "Run
  in background" take the thread out of the pane. The daemon runs its queued messages in
  the background, where no one sees them.
- **The first message after an Esc.** `tell` says `listening`, since Codex does not hold
  the message yet. Later `tell`s, `lma` and the parent see it when it has waited a minute.
- **A change to Codex's queue.** The database has no documentation; its table and columns
  are from Codex 0.166.0. If Codex renames them, lemonaid logs the read failure and sees no
  held messages.

See [recovery](recovery.md#a-codex-lemon-whose-messages-codex-holds) to bring the lemon back.

### Always-loaded docs

With [`[codex] context_doc`](config.md#codex) set, the SessionStart hook passes that file and
the files its `@` imports name to every new Codex thread, and again after `/clear` and after
each compaction (Codex reruns SessionStart then, so the docs return when compaction drops
them). An import is `@path` at the start of a line or after a space, outside code; it is
relative to the importing file, `~` expands and `\ ` is a space. Each file is included once,
imports are followed four hops deep, as in Claude Code, and a file that can't be read is logged and skipped. If the
docs were also listed for Codex to read in `~/.codex/AGENTS.md`, remove that list, or Codex
reads each one twice.

Codex otherwise cuts a hook's text past about 10 KB down to a preview of its start and end,
so `lemonaid hooks install --harness codex` sets `"additionalContextLimit": 0` on the
SessionStart handler, updating one installed by an earlier version. That changes the hook's
hash: approve it again in Codex's `/hooks` once after upgrading.

## CLI commands

```bash
# Manually trigger a notification (for testing)
lemonaid codex notify '{"type": "agent-turn-complete", "thread-id": "abc123", "cwd": "/path/to/project"}'

# Dismiss a session's notification
lemonaid codex dismiss --session-id abc123
```

`lemonaid codex turn` is called by the turn hooks (section 4) with Codex's event JSON on
stdin.

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

### Rows not marked read, or showing old activity

1. **Check the turn hook is trusted**: open `/hooks` in Codex and trust `lemonaid: turn` for
   each of its events.

2. **Check logs**:
   ```bash
   rg 'lemonaid\\.codex\\.(turns|threads|service)' /tmp/lemonaid.log
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

   That stops a Codex launch from starting the daemon. It does not stop a launch from joining a daemon that already runs: a bare `codex` in a window, a respawn, or a resume still joins one. Only `codex --no-daemon` keeps a launch off the daemon, and lemonaid's launch templates pass it. A session off the daemon runs its hooks in its own pane and records that pane's `tty`, like Claude's. `lemonaid tmux doctor` warns when the setting is missing.
