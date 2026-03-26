# Configuration Reference

Config file: `~/.config/lemonaid/config.toml`

Created automatically on first run, or with `lemonaid init`.

## `[wezterm]`

See [wezterm.md](wezterm.md).

## `[tmux-session]`

| Key | Default | Description |
|-----|---------|-------------|
| `scratch_height` | `"10"` | Default height for the scratch pane in rows. Percentages (e.g. `"15%"`) are accepted but resize detection won't work with them. |
| `follow_scratch` | `false` | Bootstrap follow mode for new tmux servers. When the scratch pane is first toggled on a server, this determines whether follow is enabled by default. See [tmux.md](tmux.md#follow-mode). |
| `resume_window` | `0` | 0-based index into the template window list: which window to replace with the resume command when spawning a tmux session from history (`T`). Set to `1` if your lemon is in the second tab. |

### `[tmux-session.templates]`

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
