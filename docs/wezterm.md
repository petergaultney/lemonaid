# WezTerm Integration

Lemonaid integrates with WezTerm to switch directly to the workspace and pane where a notification originated, and to navigate back to your previous location.

## Setup

Add the following to your `~/.config/wezterm/wezterm.lua`:

### 1. Escape sequence handler (required)

This handler responds to escape sequences sent by lemonaid to switch workspaces and panes:

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

### 2. Back navigation keybinding (optional but recommended)

This keybinding lets you toggle between your current location and the previous one with `LEADER p`. Supports ping-pong: pressing it repeatedly toggles between two locations.

```lua
-- Add to your config.keys table:
{ key = 'p', mods = 'LEADER', action = wezterm.action_callback(function(window, pane)
    -- Call lemonaid to swap: saves current location, returns target
    local lemonaid = os.getenv("HOME") .. "/.local/bin/lemonaid"
    local current_ws = wezterm.mux.get_active_workspace()
    local current_pane = pane:pane_id()
    local handle = io.popen(lemonaid .. " wezterm swap '" .. current_ws .. "' " .. tostring(current_pane))
    if not handle then return end
    local result = handle:read("*a"):gsub("%s+$", "")
    handle:close()

    -- Parse "workspace|pane_id" output
    local sep = result:find("|")
    if not sep then return end
    local target_ws = result:sub(1, sep - 1)
    local target_pane = tonumber(result:sub(sep + 1))
    if not target_ws or not target_pane then return end

    -- Switch to target workspace and pane
    window:perform_action(act.SwitchToWorkspace { name = target_ws }, pane)
    for _, w in ipairs(wezterm.mux.all_windows()) do
        for _, t in ipairs(w:tabs()) do
            for _, p in ipairs(t:panes()) do
                if p:pane_id() == target_pane then t:activate(); p:activate(); return end
            end
        end
    end
end) },
```

Change `'p'` and `'LEADER'` to match your preferred keybinding.

## How it works

### Switching to notifications

When you press Enter on a notification in the `lma` TUI:

1. Lemonaid saves your current location (workspace + pane) to `~/.local/state/lemonaid/back.json`
2. Lemonaid sends an escape sequence to WezTerm with the target workspace and pane
3. The `user-var-changed` handler receives this and switches WezTerm to the target

### Back navigation

When you press `LEADER p` (or your configured keybinding):

1. WezTerm calls `lemonaid wezterm swap <workspace> <pane_id>` with your current location
2. Lemonaid reads the saved target from `back.json`, then overwrites it with your current location
3. Lemonaid outputs the target as `workspace|pane_id`
4. WezTerm parses this and switches to the target

Because the swap is atomic (read target, write current), pressing `LEADER p` repeatedly toggles between two locations.

## CLI commands

- `lemonaid wezterm back` - Switch to the saved back location (uses escape sequences, must run in a terminal)
- `lemonaid wezterm swap <workspace> <pane_id>` - Swap back location and print target (designed for Lua integration)

## Configuration

In `~/.config/lemonaid/config.toml`:

```toml
[wezterm]
# How to resolve which pane a notification came from: "tty" or "metadata"
# "tty" queries wezterm cli list to find the pane by TTY name (recommended)
# "metadata" uses workspace/pane_id stored in notification metadata
resolve_pane = "tty"
```

## Troubleshooting

### Switching doesn't work

1. Make sure the `user-var-changed` handler is in your wezterm.lua
2. Reload WezTerm config (or restart WezTerm)
3. Check that `lemonaid` is in your PATH

### Back navigation goes to wrong location

The back location is saved when you switch TO a notification. If `back.json` has stale data:

```bash
cat ~/.local/state/lemonaid/back.json
```

You can manually clear it:

```bash
rm ~/.local/state/lemonaid/back.json
```
