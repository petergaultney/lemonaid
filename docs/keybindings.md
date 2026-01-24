# TUI Keybindings

All keybindings in the `lma` TUI are configurable via `~/.config/lemonaid/config.toml`.

## Default Keybindings

| Key | Action |
|-----|--------|
| `Enter` | Open notification (switches to that session) |
| `u` | Jump directly to earliest unread session |
| `m` | Mark as read |
| `a` | Archive (remove from list) |
| `r` | Rename session (clear to revert to auto-name) |
| `g` | Refresh |
| `q` / `Escape` | Quit |
| `↑` / `↓` | Navigate list |

## Configuration

Add a `[tui.keybindings]` section to your config:

```toml
[tui.keybindings]
quit = "q"
select = ""  # additional keys for select (Enter always works)
refresh = "g"
jump_unread = "u"
mark_read = "m"
archive = "a"
rename = "r"
up_down = ""  # arrow key alternatives (see below)
```

For example, to use `o` for selecting sessions:

```toml
[tui.keybindings]
select = "o"
```

### Multiple keys per action

Each character in the string is a separate keybinding. For example:

```toml
quit = "qQ"  # both 'q' and 'Q' will quit
```

The footer shows the first configured key.

### Arrow key alternatives

The `up_down` field accepts a 2-character string for up/down navigation:

```toml
# Vim-style
up_down = "kj"

# Norman WASD-style (right hand)
up_down = "ri"
```

Leave empty (the default) to use only arrow keys.

## Non-configurable keys

- `Enter` - built into the DataTable widget
- `Escape` - always bound to quit (in addition to configured quit key)
- `P` - patch Claude binary (only shown when Claude is unpatched)
