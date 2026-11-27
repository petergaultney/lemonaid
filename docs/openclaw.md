# OpenClaw Integration

Lemonaid supports [OpenClaw](https://openclaw.ai/), the open-source personal AI assistant, in two ways:

- **Gateway sessions as lemons.** On the machine running OpenClaw's gateway, each session (a Matrix room, a Signal chat) can be a lemon with a brief, mail and watchers. See below.
- **Following a TUI session** from your inbox, described from [How It Works](#how-it-works) on.

## Gateway sessions as lemons

OpenClaw is two things to lemonaid, kept apart:

- **The harness** is the gateway. It runs each turn, and a session's identity is its session key, such as `agent:main:matrix:channel:!room:server`. Lemonaid lists sessions with `openclaw sessions --all-agents --json` and wakes one with `openclaw gateway call agent`.
- **The front end** is the chat room the session lives in (`openclaw-chat`). Showing the lemon does nothing. Prompting it, as the web grove's lemon page does, sends the text with `chat.send`, which the session takes as its user's. A command a session runs is in this front end, so `lemon start` from it opens a new session beside it.

### Registering a session

Run this inside the session, with the key its `session_status` tool reports:

```sh
lemonaid openclaw register --session-key 'agent:main:matrix:channel:!room:server'
```

The session's inbox row is `openclaw:<session key>`. A shell command OpenClaw runs carries the Codex thread underneath the session (`CODEX_THREAD_ID`) but nothing naming the session, so registering records that thread, and `--self` commands from the session find their lemon by it. OpenClaw starts a new thread after a reset or compaction; `--self` then refuses with a reminder to register again, rather than mistaking the session for a Codex lemon.

A lemon that registers another session, such as one it spawned, keeps its own thread: the other session keeps whatever thread it had. If a thread was given to the wrong session, run the command inside the right one with `--claim` to take it back.

### Starting a lemon from a session

Run inside a session, `lemonaid lemon start` opens a new session of the same agent instead of a terminal window:

```sh
lemonaid lemon start --brief <brief> --parent self
```

The new session is an ordinary one, as the dashboard's New Session makes (`agent:<agent>:dashboard:<id>`), not a subagent: OpenClaw doesn't announce its runs to the session that started it or tell it about the new session's messages. Its parent is lemonaid's alone, and hears only of its brief's status. Lemonaid registers it, attaches the brief, and sends the first prompt with `chat.send`; that prompt first asks the session to register itself, which binds the Codex thread its `--self` commands carry. `--preset`, `--shape`, `--docs`, `--lemon-arg` and `--dry-run` are refused, since the session runs its agent's own model and docs.

`lemonaid brief handoff --to openclaw` moves a brief into a new session the same way, once the outgoing lemon has written its `## Handoff`. That replaces a session OpenClaw started as a subagent with an ordinary one: run it with `--source <Lemon-ID>` for the subagent's lemon. A lemon archived as quiet can be handed off; the request restores it. The outgoing lemon stays archived after the handoff, even when its old session gets another message.

### Every conversation in the grove

```sh
lemonaid openclaw sync [--days 90]
```

makes each conversation session active in the last 90 days a lemon: Matrix rooms, Signal, WhatsApp and Telegram chats, and each agent's main session. Cron runs, worker sessions and the threads within a chat, each a session of its own, are left out. A lemon runs in its agent's workspace and is named for its agent and chat (`Ada - Signal`, `Ada - room r00mA1`); an agent made for one room takes the agent's name. In the grove each conversation is its own tree, though many share a workspace; the grove window's list leaves its long session id out of the title, and shows it in the tree's card on hover. Renaming one in lemonaid keeps your name. When a conversation goes quiet, the sync archives its lemon, unless it has a brief; it comes back when the conversation does. A lemon you archive yourself, from the grove or the inbox, comes back when its conversation gets a new message, as other lemons do. Each lemon's age counts from its conversation's last message.

The sync also binds each conversation's lemon to the Codex thread running it, which OpenClaw's Codex plugin records in OpenClaw's state database (`~/.openclaw/state/openclaw.sqlite`), so `--self` commands from the session find their lemon without registering, and find it again after OpenClaw moves the session to a new thread, within a minute. That record is the plugin's own and not a published interface; if it is missing or reads differently, the sync logs it and a session registers itself as above.

Archiving a session in OpenClaw (`openclaw sessions archive`, or the Control UI) archives its lemon, whoever registered it and whether or not it has a brief, as closing a Claude or Codex session does. When OpenClaw restores the session, by hand or because a new message arrived in its room, the lemon comes back as it was.

To keep it current, run

```sh
lemonaid openclaw observe [--days 90] [--every 60]
```

on the machine running the gateway, as a systemd user service beside the gateway's. It syncs once a minute until stopped, and logs a sync that fails rather than exiting. It also keeps a connection to the gateway open and records each session's turn from its events, so every grove shows an OpenClaw lemon as working from its turn's first event until it ends or fails; a dropped connection is opened again on the next round. This needs the `openclaw` extra. Nothing else runs the sync: the web grove (`lemonaid grove serve`) shows what it finds, but serving the grove doesn't start it, and observing doesn't need the grove.

### Briefs, mail and watchers

Once registered, the session uses briefs like any lemon: `lemonaid brief attach --self <brief>`, `lemonaid brief id --self`, and the rest. `lemonaid watch --self --push` starts its scout in the scout host, which turns each batch (mail, doc comments, PR events, children) into one gateway turn in the session. `lemonaid tell` to the lemon starts the scout if none runs.

OpenClaw runs a session's turns one at a time, and no hook records the files a turn writes. So the scout holds every batch while the session is mid-turn (as `lemonaid openclaw observe` records it, and from the moment the scout sends a turn); without the observer running, nothing holds the batches, and sends one turn for everything that arrived once the session is idle. A doc body change the scout sees appear while a turn runs is recorded as the lemon's own edit, as Claude Code's hooks record one, so it wakes nobody, even after later turns; a change made by someone else during the turn counts as the lemon's too.

When the command that starts the scout host runs inside a systemd service (as the gateway's shell commands do), the host gets a transient user unit of its own, so a gateway restart doesn't stop it.

## How It Works

1. **Session registration** - Register from within the TUI using `!lemonaid openclaw register`
2. **Activity updates** - The watcher monitors the session and shows what OpenClaw is doing
3. **Turn-complete detection** - When the agent finishes (`stopReason: "stop"`), notification is marked as needing attention
4. **Auto-dismiss** - When you provide input, the notification is marked as read

## Setup

### Quick Start (Recommended)

From within your OpenClaw TUI session, run:

```
!lemonaid openclaw register
```

This registers the current session with lemonaid and captures the TTY for tmux pane switching. You only need to do this once per session.

**Why this works:** OpenClaw's `!` prefix runs shell commands as a child of the TUI process, which means the command inherits the TUI's terminal context (TTY). Gateway-based hooks can't capture this because they run in a separate process.

### Hook-Based Registration (Optional)

You can also set up a hook to auto-register new sessions, though this won't capture the TTY (uses cwd-based pane matching instead).

Create `~/.openclaw/hooks/lemonaid-notify/HOOK.md`:

```markdown
---
name: lemonaid-notify
description: Register OpenClaw sessions with lemonaid inbox
metadata:
  openclaw:
    emoji: "🍋"
    events:
      - agent:bootstrap
---
```

Create `~/.openclaw/hooks/lemonaid-notify/handler.ts`:

```typescript
import { exec } from "child_process";
import type { HookHandler } from "@openclaw/sdk";

const handler: HookHandler = async (event) => {
  const sessionId = event.context?.sessionKey || "";
  const cwd = event.context?.workspace || process.cwd();
  const cmd = `lemonaid openclaw notify --session-id "${sessionId}" --cwd "${cwd}"`;
  exec(cmd, (error) => {
    if (error) console.error("lemonaid notify failed:", error);
  });
};

export default handler;
```

Enable with: `openclaw hooks enable lemonaid-notify`

**Note:** Hook-based registration runs in the Gateway process, not the TUI, so it can't capture the TTY. Use `!lemonaid openclaw register` from the TUI after the hook creates the entry to add the TTY.

## Session Storage

OpenClaw stores sessions at:
- **Sessions**: `~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl`
- **Index**: `~/.openclaw/agents/<agentId>/sessions/sessions.json`
- **Config**: `~/.openclaw/openclaw.json`

## CLI Commands

```bash
# Register current session (run from TUI with ! prefix)
!lemonaid openclaw register

# Manually add a notification
lemonaid openclaw notify --session-id <id> --cwd /path/to/project

# Mark a session as read
lemonaid openclaw dismiss --session-id <id>
```

### Shell Shortcut

OpenClaw's `!` commands run in `/bin/sh`, not your normal shell, so aliases won't work. If `!lemonaid openclaw register` is too long to type, create a short wrapper script:

```bash
mkdir -p ~/bin && cat > ~/bin/lreg << 'EOF'
#!/bin/sh
exec lemonaid openclaw register "$@"
EOF
chmod +x ~/bin/lreg
```

Make sure `~/bin` is in your PATH, then from the OpenClaw TUI: `!lreg`

## Remote Sessions (SSH)

If OpenClaw runs on a remote machine (e.g., sessions stored on a gateway server), lemonaid can read session files via SSH.

### Setup

Add to `~/.config/lemonaid/config.toml`:

```toml
[openclaw]
remote_host = "my-server"  # SSH host where session files live
```

The value is passed directly to `ssh`, so it supports `user@host` format (e.g., `"me@my-server"`). You can also configure the user in `~/.ssh/config` instead:

```
Host my-server
    User me
```

With `remote_host` enabled, registration prefers the most recent remote session that is not
already registered to a different OpenClaw TTY. You can also target a specific session with
`lemonaid openclaw register --session-id <id_or_prefix>`.

### SSH ControlMaster (Recommended)

The watcher polls every 0.5s. To avoid opening a new SSH connection each time, configure connection multiplexing in `~/.ssh/config`:

```
Host my-server
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 600
```

Create the sockets directory: `mkdir -p ~/.ssh/sockets`

The first `ssh my-server` opens a real connection. Subsequent ones reuse the socket (near-instant).

### How It Works

- **Registration**: `!lemonaid openclaw register` SSHes to the remote host, lists recent sessions, and picks the best candidate for the current TTY.
- **Polling**: The watcher reads session file tails via `ssh <host> "tail -c 65536 '<path>'"` each cycle.
- **TTY/pane switching**: Still works because the TUI runs locally — only the session files are remote.

## Troubleshooting

### Sessions not appearing

1. Check OpenClaw is storing sessions in `~/.openclaw/agents/`
2. Verify session files exist with `ls ~/.openclaw/agents/*/sessions/*.jsonl`
3. For remote: `ssh my-server "ls ~/.openclaw/agents/*/sessions/*.jsonl"`
4. Check watcher logs: `grep openclaw /tmp/lemonaid.log`

### Activity not updating (local)

The watcher reads the last 64KB of each session file. If sessions are very large, activity detection may lag.

### Activity not updating (remote)

1. Verify SSH works: `ssh my-server "tail -c 100 ~/.openclaw/agents/*/sessions/*.jsonl"`
2. Check for SSH timeouts in logs: `grep "ssh.*timed out" /tmp/lemonaid.log`
3. Ensure ControlMaster is configured (see above) to avoid connection overhead

## Technical Notes

- Channel format: `openclaw:<session_id_prefix>`
- Entry types watched: `message`, `custom_message`, `compaction`
- Dismissal triggers: assistant/user messages, `custom_message`, and `compaction`
- Turn-complete detection: `stopReason: "stop"` in assistant messages marks notification as needing attention
- Logs: `grep openclaw /tmp/lemonaid.log` (uses `openclaw.watcher`, `openclaw.notify`, `openclaw.ssh` logger names)

### TTY Detection

OpenClaw TypeScript hooks run in a Node.js process that doesn't have a TTY directly attached. To enable tmux pane switching, lemonaid walks up the process tree to find an ancestor shell's TTY. This uses the `ps` command which works on both macOS and Linux.

If TTY detection fails (e.g., very deep process nesting), lemonaid falls back to matching panes by working directory. This fallback may be ambiguous if multiple sessions share the same cwd.
