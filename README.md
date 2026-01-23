# lemonaid

Attention inbox for managing notifications from lemons (go on, say LLMs three times fast)
when you live in the CLI.

<img width="943" height="285" alt="Screenshot 2026-01-16 at 11 43 47" src="https://github.com/user-attachments/assets/d7ad9984-9668-4977-a0b3-4f54b43cf2ae" />

Eventually other tools will get packaged here as well.

## Features

- **Notification inbox**: Track which Claude Code sessions need your attention
- **Terminal integration**: Hit enter to jump directly to the waiting session's pane (supports [tmux](docs/tmux.md) and [WezTerm](docs/wezterm.md))
- **Back navigation**: Toggle between your inbox and the session you jumped to
- **Auto-refresh TUI**: See new notifications appear without losing your place
- **Upsert behavior**: Repeated notifications update timestamp instead of creating duplicates
- **tmux session templates**: Spin up new Claude workspaces with a predefined window layout

## Installation

```bash
# Install globally with uv
uv tool install --editable ~/play/lemonaid

# For development
cd ~/play/lemonaid
uv sync
uv run pre-commit install
```

## Usage

```bash
# Open the inbox TUI
lma

# Or via the full CLI
lemonaid inbox

# List notifications (non-interactive)
lemonaid inbox list
```

### TUI Keybindings

| Key | Action |
|-----|--------|
| `Enter` | Open notification (switches to that session) |
| `d` | Mark as read (dismiss) |
| `r` / `g` | Refresh |
| `q` / `Escape` | Quit |

### Programmatic Access

For JSON output and programmatic access (useful for lemons), see [docs/for-lemons.md](docs/for-lemons.md).

## Claude Code Integration

Add these hooks to your `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "lemonaid claude dismiss"
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
    ],
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "lemonaid claude dismiss"
          }
        ]
      }
    ]
  }
}
```

This gives you:
- **Stop hook**: Notification when Claude finishes responding
- **Notification hook**: Notification when Claude needs permission
- **UserPromptSubmit hook**: Dismisses notification when you send a message
- **PreToolUse hook** (recommended): Dismisses notification whenever Claude runs a tool

The `PreToolUse` hook is important because granting a permission prompt doesn't trigger `UserPromptSubmit`. Without it, you'll see stale "permission needed" notifications after granting permission, since Claude continues working but the notification remains unread until your next prompt.

**Known limitation**: There's no Claude Code hook for "permission granted" or "Claude is thinking." After you grant a permission, Claude may think for a few seconds before invoking the next tool. During this gap, no hook fires, so the notification briefly stays unread. This is unavoidable with current Claude Code hook events.

## Terminal Setup

- **tmux**: See [docs/tmux.md](docs/tmux.md) for pane switching, back navigation, session templates, and window colors
- **WezTerm**: See [docs/wezterm.md](docs/wezterm.md) for workspace/pane switching setup

## Configuration

Config file: `~/.config/lemonaid/config.toml`

```toml
[handlers]
# Map channel patterns to handlers
"claude:*" = "tmux"  # or "wezterm"
```

See the terminal-specific docs for additional configuration options.

## Architecture

- **inbox**: SQLite-backed notification storage with Textual TUI
- **handlers**: Pluggable system for handling notifications (wezterm, exec)
- **claude**: Claude Code hook integration for notify/dismiss
