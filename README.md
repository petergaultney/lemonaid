# lemonaid

Attention inbox for managing notifications from LLMs ("lemons") and other background tools.

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

For workspace/pane switching to work, add this to your `~/.config/wezterm/wezterm.lua`:

```lua
local wezterm = require 'wezterm'
local act = wezterm.action

wezterm.on('user-var-changed', function(window, pane, name, value)
  if name == "switch_workspace_and_pane" then
    local sep = value:find("|")
    if sep then
      local workspace = value:sub(1, sep - 1)
      local target_pane_id = tonumber(value:sub(sep + 1))

      window:perform_action(
        wezterm.action_callback(function(win, p)
          win:perform_action(act.SwitchToWorkspace { name = workspace }, p)

          local mux = wezterm.mux
          for _, mux_win in ipairs(mux.all_windows()) do
            for _, tab in ipairs(mux_win:tabs()) do
              for _, tab_pane in ipairs(tab:panes()) do
                if tab_pane:pane_id() == target_pane_id then
                  tab:activate()
                  tab_pane:activate()
                  return
                end
              end
            end
          end
        end),
        pane
      )
    end
  end
end)
```

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
