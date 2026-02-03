# OpenClaw Integration

Lemonaid supports [OpenClaw](https://openclaw.ai/), the open-source personal AI assistant.

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

### Shell Alias

OpenClaw's `!` commands run in `/bin/sh`, not your normal shell, so aliases won't work. Create a script instead:

```bash
mkdir -p ~/sw/bin && cat > ~/sw/bin/lreg << 'EOF'
#!/bin/sh
exec lemonaid openclaw register "$@"
EOF
chmod +x ~/sw/bin/lreg
```

Make sure `~/sw/bin` is in your PATH, then from OpenClaw TUI: `!lreg`

## Troubleshooting

### Sessions not appearing

1. Check OpenClaw is storing sessions in `~/.openclaw/agents/`
2. Verify session files exist with `ls ~/.openclaw/agents/*/sessions/*.jsonl`
3. Check watcher logs: `tail -f /tmp/lemonaid-watcher.log`

### Activity not updating

The watcher reads the last 64KB of each session file. If sessions are very large, activity detection may lag.

## Technical Notes

- Channel format: `openclaw:<session_id_prefix>`
- Entry types watched: `message`, `custom_message`, `compaction`
- Dismissal triggers: user messages, assistant activity
- Turn-complete detection: `stopReason: "stop"` in assistant messages marks notification as needing attention

### TTY Detection

OpenClaw TypeScript hooks run in a Node.js process that doesn't have a TTY directly attached. To enable tmux pane switching, lemonaid walks up the process tree to find an ancestor shell's TTY. This uses the `ps` command which works on both macOS and Linux.

If TTY detection fails (e.g., very deep process nesting), lemonaid falls back to matching panes by working directory. This fallback may be ambiguous if multiple sessions share the same cwd.
