# tmux Integration

Lemonaid integrates with tmux to switch directly to the session and pane where a notification originated, and to navigate back to your previous location.

## Setup

### 1. Configure lemonaid to use tmux

In `~/.config/lemonaid/config.toml`:

```toml
[handlers]
"claude:*" = "tmux"
```

### 2. Add a back-navigation keybinding (optional but recommended)

Add to your `~/.tmux.conf`:

```tmux
# Lemonaid: toggle between current and previous location
bind-key p run-shell ' \
    target=$(lemonaid tmux swap "#{session_name}" "#{pane_id}"); \
    if [ -n "$target" ]; then \
        tmux switch-client -t "$(echo "$target" | cut -d"|" -f2)"; \
    fi'
```

This binds `prefix + p` to toggle between your current location and the previous one (ping-pong style).

Reload tmux config:

```bash
tmux source-file ~/.tmux.conf
```

## How it works

### Switching to notifications

When you press Enter on a notification in the `lma` TUI:

1. Lemonaid looks up the TTY from the notification metadata
2. Queries tmux to find which session/pane owns that TTY
3. Saves your current location to `~/.local/state/lemonaid/tmux-back.json`
4. Runs `tmux switch-client -t <pane_id>` to switch to the target

### Back navigation

When you press `prefix + p`:

1. tmux calls `lemonaid tmux swap <session> <pane_id>` with your current location
2. Lemonaid reads the saved target, then saves your current location
3. Lemonaid outputs the target as `session|pane_id`
4. tmux switches to the target pane

Because the swap is atomic, pressing `prefix + p` repeatedly toggles between two locations.

## CLI commands

- `lemonaid tmux back` - Switch to the saved back location
- `lemonaid tmux swap <session> <pane_id>` - Swap back location and print target (for keybinding integration)

## Advantages over WezTerm integration

- **Simpler**: Direct CLI commands, no escape sequences or Lua callbacks
- **More reliable**: tmux's architecture is simpler and more predictable
- **Portable**: Works with any terminal emulator
- **Debuggable**: Easy to test commands manually

## Troubleshooting

### Switching doesn't work

1. Make sure you're running inside tmux (`echo $TMUX` should show something)
2. Check that the notification has TTY metadata: `lemonaid inbox list --json | jq`
3. Test manually: `tmux switch-client -t %5` (replace %5 with actual pane ID)

### Back navigation goes to wrong location

Check the saved location:

```bash
cat ~/.local/state/lemonaid/tmux-back.json
```

Clear it if stale:

```bash
rm ~/.local/state/lemonaid/tmux-back.json
```
