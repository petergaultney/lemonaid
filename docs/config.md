# Configuration Reference

Config file: `~/.config/lemonaid/config.toml`

Created automatically on first run, or with `lemonaid init`.

## `[backends.<name>]`

Per-backend configuration. `<name>` is the backend prefix (`claude`, `codex`, `openclaw`, `opencode`, or any custom backend).

| Key | Default | Description |
|-----|---------|-------------|
| `resume_command` | *(built-in per backend)* | Shell command template for resuming a session. Placeholders like `{session_id}` are filled from notification metadata, then the result is `shlex.split` into argv. |

Built-in defaults (used when no `resume_command` is configured):

| Backend | Default |
|---------|---------|
| `claude` | `lemonaid claude resume {session_id}` |
| `codex` | `codex resume {session_id}` |
| `openclaw` | `openclaw --session {session_key}` |
| `opencode` | `opencode --session {session_id}` |

To add flags to Claude resumes:

```toml
[backends.claude]
resume_command = "lemonaid claude --allow-dangerously-skip-permissions --resume {session_id}"
```

## `[wezterm]`

See [wezterm.md](wezterm.md).

## `[tmux-session]`

| Key | Default | Description |
|-----|---------|-------------|
| `scratch_position` | `"top"` | Which edge the scratch pane starts against: `top` or `left`. Move it at runtime with `--flip` or `f` in `lma`; that choice is remembered per tmux server. |
| `scratch_height` | `"10"` | Height of the scratch pane on top, in rows. |
| `scratch_width` | `"45"` | Width of the scratch pane on the left, in columns. |
| `follow_scratch` | `false` | Bootstrap follow mode for new tmux servers. When the scratch pane is first toggled on a server, this determines whether follow is enabled by default. See [tmux.md](tmux.md#follow-mode). |
| `resume_window` | `0` | 0-based index into the template window list: which window to replace with the resume command when spawning a tmux session from history (`T`). Set to `1` if your lemon is in the second tab. |

### `[tmux-session.templates]`

See [tmux.md](tmux.md).

## `[tmux-window]`

| Key | Default | Description |
|-----|---------|-------------|
| `named_processes` | `[]` | Console-script or application names to show by themselves in the tmux status line when they run behind Python, Node, or another recognized interpreter. |

For example, to show `mops-console` instead of its working-directory name:

```toml
[tmux-window]
named_processes = ["mops-console"]
```

The name may come from the interpreter's command line or the pane title. Add
`#{pane_pid}` as the final `lemonaid-tmux-window-status` argument, as shown in
[the tmux setup](tmux.md#tmuxconf-setup), for command-line detection.

## `[tui]`

| Key | Default | Description |
|-----|---------|-------------|
| `transparent` | `false` | Use ANSI colors instead of RGB, allowing terminal transparency to work. |
| `card_unread_style` | `"dot"` | Card-layout unread treatment: `"dot"`, or `"bar"` for a yellow title bar and provider-coloured model badge. |

With `card_unread_style = "bar"`, an unread card drops the dot and paints its
first line instead. The selector and title use a lemon-yellow background with
black text; the model label uses its provider colour as the background, with
one coloured space on each side. A green selected-session bar remains green.
The otherwise-empty blue/yellow table header is hidden in card layout because
the unread rows now carry the status themselves.

```toml
[tui]
card_unread_style = "bar"
```

### `[tui.backend_labels]`

Override the label shown for each backend in the session list when its model is not yet known. Keys are backend names (`claude`, `codex`, `openclaw`); values are any string. Claude, Codex, and OpenClaw default to `Anthropic`, `OpenAI`, and `🦞`; unknown backends display their name as-is.

```toml
[tui.backend_labels]
claude = "Claude"
codex = "Codex"
openclaw = "🦞"
```

When the session transcript names a recognized model family, its friendly name and version replace the backend fallback: for example, `Opus 5.5`, `Fable 5.6`, or `Sol 5.6`. Labels are right-aligned and use the provider's color.

### `[tui.keybindings]`

See [keybindings.md](keybindings.md).

## Environment variables

| Variable | Effect |
|----------|--------|
| `LEMONAID_DB` | Path to the inbox database, replacing `~/.local/share/lemonaid/lemonaid.db`. A second `lma` pointed at its own file cannot archive rows in your real inbox, which is what makes demos and experiments safe - `scripts/demo-inbox.py` uses it. |
| `LEMONAID_DEBUG` | `1` turns on debug logging in the hook entry points. |
| `LEMONAID_LOG_FILE` | Path to write those debug logs to. |
