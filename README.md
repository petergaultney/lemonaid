# lemonaid

A toolkit for working with lemons (LLMs). Because when life gives you lemons, you need some aid managing them.

## Features

### Inbox (`lma`)

Attention inbox for managing notifications from Claude Code and other LLM tools. Think of it as an "unread messages" system for your background AI sessions.

- Track which lemons need your attention
- TUI for quick navigation
- WezTerm integration for instant workspace/pane switching
- Works with Claude Code hooks, extensible to other tools

## Installation

```bash
# With uv
uv pip install -e ~/play/lemonaid

# Or install globally
pipx install ~/play/lemonaid
```

## Usage

```bash
# Launch the inbox TUI (quick access)
lma

# Or via the main CLI
lemonaid inbox

# Add a notification (for testing or scripting)
lemonaid inbox add "claude:abc123" "Waiting for input" --metadata '{"workspace": "my-project", "pane_id": 42}'

# List unread notifications
lemonaid inbox list
```

## Claude Code Integration

Add to your `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "idle_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "lemonaid inbox add \"claude:$SESSION_ID\" \"Waiting for input\" --metadata '{...}'"
          }
        ]
      }
    ]
  }
}
```

## WezTerm Integration

The inbox TUI can switch directly to a WezTerm workspace and pane when you "open" a notification. Requires the `switch_workspace_and_pane` user-var handler in your `wezterm.lua`.

## Future Ideas

- More lemon-related tools as needs arise
- Better Claude Code session tracking
- Integration with other AI tools (Codex, etc.)
