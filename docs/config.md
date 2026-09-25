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
| `harness_window` | `resume_window` | 0-based template window whose command accepts `place open --prompt`. Set it separately only when new-session prompts and resumed sessions belong in different windows. |

### `[tmux-session.templates]`

See [tmux.md](tmux.md).

Template names also act as harness names for `place open`. For example,
`place open feat/thing --harness codex` selects the `codex` list below, while
an open without `--harness` continues to select `default`:

```toml
[tmux-session]
resume_window = 1
# harness_window = 1  # implied by resume_window when omitted

[tmux-session.templates]
default = [
    "emacsclient -nw .",
    "lemonaid claude patch && claude --remote-control --thinking-display summarized",
    "",
]
codex = ["emacsclient -nw .", "codex", ""]
```

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
| `brief_status` | `false` | In card layout, color sessions with attached briefs by their `Status:` and show brief age. |
| `brief_stale_hours` | `6` | Mark `working` and `waiting` cards stale after this many hours without a brief edit. |

With `brief_status = true`, attached briefs give `blocked` cards a yellow
headline, `done` cards a blue headline, and `waiting` cards dimmer text.
Right under the name and location, a card shows the first line of `Needs` from
`## Now` with its label (`Needs Peter: ...`) in the attention colour, then the
brief age, then, for a `waiting` brief, the first line of `Waiting on`. `working` cards retain the read style.
Every brief card shows its age. Unread remains a separate dot, including when
`card_unread_style = "bar"`. Cards without an attached brief retain their
current appearance. This setting only changes cards, not the column layout.
Sessions sort by brief status in both layouts whether or not it is set; see
[Session order](../README.md#session-order).

```toml
[tui]
brief_status = true
brief_stale_hours = 6
```

With `card_unread_style = "bar"`, an unread card drops the dot and paints its
first line instead. The selector and title use a lemon-yellow background with
black text; the model label uses its provider colour as the background, with
one coloured space on each side. Session emojis appear at the right end of the
second line, just before the pin marker when present. A green selected-session
bar remains green.
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

## `[brief]`

| Key | Default | Description |
|-----|---------|-------------|
| `pr_state` | `""` | Shell command that prints a PR's state for `{ref}`; unset shows PR numbers without a state. |

The brief popup and sidebar run `pr_state` for each `PR #N` or pull-request URL
in a brief (up to three), in the lemon's place, so a bare number resolves against
that directory's repository. `{ref}` is the number or URL, shell-quoted. The
first word printed must be `open`, `draft`, `merged` or `closed`; anything else,
a non-zero exit, or more than 5 seconds shows no state. lemonaid knows nothing
about the forge, so any tool works. With GitHub's `gh`:

```toml
[brief]
pr_state = "gh pr view {ref} --json state,isDraft --jq 'if .isDraft then \"draft\" else (.state | ascii_downcase) end'"
```

The popup runs it once per open. The sidebar re-renders on a timer, so it caches
each answer for two minutes and fetches in the background.

## Environment variables

| Variable | Effect |
|----------|--------|
| `LEMONAID_DB` | Path to the inbox database, replacing `~/.local/share/lemonaid/lemonaid.db`. A second `lma` pointed at its own file cannot archive rows in your real inbox, which is what makes demos and experiments safe - `scripts/demo-inbox.py` uses it. |
| `LEMONAID_CONFIG` | Path to the config file, replacing `~/.config/lemonaid/config.toml`. |
| `LEMONAID_STATE_DIR` | Directory for scratch-pane and back-location state, replacing `~/.local/state/lemonaid`. |

`scripts/sandbox` sets all three, plus a private tmux socket, to run a checkout against a snapshot of your state without touching the real one.
| `LEMONAID_DEBUG` | `1` turns on debug logging in the hook entry points. |
| `LEMONAID_LOG_FILE` | Path to write those debug logs to. |
