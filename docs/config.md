# Configuration Reference

Config file: `~/.config/lemonaid/config.toml`

Created automatically on first run, or with `lemonaid init`.

## `[wezterm]`

See [wezterm.md](wezterm.md).

## `[tmux-session.templates]`

See [tmux.md](tmux.md).

## `[tui]`

| Key | Default | Description |
|-----|---------|-------------|
| `transparent` | `false` | Use ANSI colors instead of RGB, allowing terminal transparency to work. |

### `[tui.backend_labels]`

Override the short label shown for each backend in the session list. Keys are backend names (`claude`, `codex`, `openclaw`); values are any string. Backends without an override display their name as-is.

```toml
[tui.backend_labels]
claude = "CC"
codex = "cx"
openclaw = "🦞"
```

### `[tui.keybindings]`

See [keybindings.md](keybindings.md).
