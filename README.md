# lemonaid

Attention inbox for managing notifications from lemons (go on, say LLMs three times fast)
when you live in the CLI.

<img width="943" height="285" alt="Screenshot 2026-01-16 at 11 43 47" src="https://github.com/user-attachments/assets/d7ad9984-9668-4977-a0b3-4f54b43cf2ae" />

Eventually other tools will get packaged here as well.

## Features

- **Notification inbox**: Track which Claude Code sessions need your attention
- **WezTerm integration**: Jump directly to the waiting session's workspace and pane
- **Auto-refresh TUI**: See new notifications appear without losing your place
- **Upsert behavior**: Repeated notifications update timestamp instead of creating duplicates

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
    ]
  }
}
```

This gives you:
- **Stop hook**: Notification when Claude finishes responding
- **Notification hook**: Notification when Claude needs permission
- **UserPromptSubmit hook**: Dismisses notification when you send a message

## WezTerm Setup

For workspace/pane switching and back navigation, see [docs/wezterm.md](docs/wezterm.md) for full setup instructions.

## Configuration

Config file: `~/.config/lemonaid/config.toml`

```toml
[handlers]
# Map channel patterns to handlers
"claude:*" = "wezterm"

[wezterm]
# How to resolve pane: "tty" or "metadata"
resolve_pane = "tty"
```

## Architecture

- **inbox**: SQLite-backed notification storage with Textual TUI
- **handlers**: Pluggable system for handling notifications (wezterm, exec)
- **claude**: Claude Code hook integration for notify/dismiss
