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
- `lemonaid tmux scratch` - Toggle the scratch lma pane (see below)
- `lemonaid tmux new [name]` - Create a new tmux session from a template

## Scratch Pane

The scratch pane provides an always-available lma inbox that can be toggled with a keybinding. Unlike running `lma` in a popup, the scratch pane stays running in the background, so there's no startup delay when showing it.

### Setup

Add to your `~/.tmux.conf`:

```tmux
# Toggle scratch lma pane
bind-key l run-shell 'lemonaid tmux scratch'
```

Reload tmux config:

```bash
tmux source-file ~/.tmux.conf
```

### Usage

1. Press `prefix + l` to show the lma inbox as a split at the top of your current window
2. Select a notification with Enter - you'll switch to that session and the lma pane auto-hides
3. Press `prefix + l` again to bring it back

### How it works

1. First toggle creates a tmux session (`_lma_scratch`) running `lma --scratch`
2. The pane is joined into your current window as a 30% top split
3. When you select a notification, lma auto-dismisses by breaking the pane to its own window
4. Subsequent toggles show/hide the same pane (no restart, instant response)

State is tracked per tmux server in `~/.local/state/lemonaid/scratch-pane-<server>.json`, so multiple tmux servers won't conflict.

### Options

```bash
# Customize the pane height
lemonaid tmux scratch --height 40%

# See what action was taken
lemonaid tmux scratch -v  # prints: created, shown, or hidden
```

## Session Templates

Create tmux sessions with a predefined window layout using `lemonaid tmux new`.

### Configuration

Add templates to `~/.config/lemonaid/config.toml`:

```toml
[tmux-session.templates]
default = [
    "emacsclient -nw .",
    "claude",
    "lma",
    "",
]
```

Each entry in the list creates a window. Empty string means just a shell.

### Usage

```bash
# Create session named after current directory, using "default" template
lemonaid tmux new

# Create session with explicit name
lemonaid tmux new my-feature

# Use a different template
lemonaid tmux new --from no-emacs

# Create in a specific directory
lemonaid tmux new --dir ~/work/project

# Create detached (don't switch to it)
lemonaid tmux new -d
```

### Claude session naming

Lemonaid automatically derives notification names from the tmux session name, so Claude sessions created with `lemonaid tmux new` will show the session name in the inbox without any extra configuration.

If you want to also set Claude's internal session name (via `/rename`), you can use:

```bash
lemonaid tmux new --rename
```

Note: Due to tmux timing issues, the Enter key may not be submitted automatically - you may need to press Enter yourself to confirm the rename.

## Window Colors

Lemonaid includes `lemonaid-tmux-window-status`, a tool that formats tmux window titles with deterministic colors based on directory names. Each directory gets a consistent color, making it easy to visually identify windows at a glance.

### tmux.conf setup

```tmux
# Enable true color support
set-option -g default-terminal "tmux-256color"
set-option -sa terminal-features ',xterm-256color:RGB'

# Window status with colored directory names
# Third argument is pane_title - used to show app names instead of "python3.12"
setw -g window-status-format " #I:#(lemonaid-tmux-window-status '#{pane_current_path}' '#{pane_current_command}' '#{pane_title}') "
setw -g window-status-current-format " #I:#(lemonaid-tmux-window-status '#{pane_current_path}' '#{pane_current_command}' '#{pane_title}') "
setw -g window-status-style none
setw -g window-status-current-style "bg=colour238,bold"
setw -g window-status-separator "│"
```

### Shell integration

For `#{pane_current_path}` to work, your shell must report the current directory to tmux via OSC 7 escape sequences. Add the appropriate snippet for your shell:

#### Bash

```bash
# Add to ~/.bashrc
if [ -n "$TMUX" ]; then
    __tmux_osc7() {
        printf '\ePtmux;\e\e]7;file://%s%s\e\e\\\e\\' "$HOSTNAME" "$PWD"
    }
    PROMPT_COMMAND="__tmux_osc7${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
fi
```

#### Zsh

```zsh
# Add to ~/.zshrc
if [[ -n "$TMUX" ]]; then
    __tmux_osc7() {
        printf '\ePtmux;\e\e]7;file://%s%s\e\e\\\e\\' "$HOST" "$PWD"
    }
    add-zsh-hook chpwd __tmux_osc7
    __tmux_osc7  # run on startup
fi
```

#### Fish

```fish
# Add to ~/.config/fish/config.fish
if set -q TMUX
    function __tmux_osc7 --on-variable PWD
        printf '\ePtmux;\e\e]7;file://%s%s\e\e\\\e\\' (hostname) "$PWD"
    end
    __tmux_osc7  # run on startup
end
```

#### Xonsh

```python
# Add to ~/.xonshrc
import platform
if "TMUX" in ${...}:
    @events.on_chdir
    def _report_cwd_to_tmux(olddir, newdir, **kw):
        print(f"\x1bPtmux;\x1b\x1b]7;file://{platform.node()}{newdir}\x1b\x1b\\\x1b\\", end="", flush=True)
    _report_cwd_to_tmux(None, os.getcwd())  # run on startup
```

### App title integration

When running Python/Node apps, tmux shows the interpreter name (e.g., "python3.12") instead of the app name. To fix this, apps can set the terminal title:

```python
# Set terminal title on startup
import sys
sys.stdout.write("\033]0;myapp\007")
sys.stdout.flush()
```

`lemonaid-tmux-window-status` will prefer `#{pane_title}` over `#{pane_current_command}` when the process is an interpreter (python, node, etc.) and the title looks meaningful.

### Customization

Edit `src/lemonaid/tmux/window_color.py` to customize:

- `COLORS` - The color palette (23 distinct colors)
- `DIR_COLORS` - Override colors for specific directory names
- `PROCESS_COLORS` - Override colors for specific process names
- `HIDDEN_PROCESSES` - Shells/wrappers that shouldn't appear (just show directory)
- `INTERPRETER_PROCESSES` - Interpreters where pane_title is preferred

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
