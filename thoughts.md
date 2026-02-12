# Lemonaid Feature Ideas

## Switch-Handler API Redesign

### The Problem with Current `[handlers]` Config

The current config asks users to map channel patterns to handlers:

```toml
[handlers]
"claude:*" = "tmux"
"codex:*" = "wezterm"
```

This is redundant. When a notification is created, we already detect and store the terminal environment it came from (as `terminal_env` in the database). The notification *knows* it came from tmux - why should the user have to tell us to use the tmux handler?

Additionally, the current design conflates switching with side-effects. If you want to run a command when switching (`exec:...`), it replaces the switch handler rather than supplementing it.

### Proposed: Switch-Handlers Named After Switch-Source

**Core insight**: The switch-source (where notification originated) determines the handler. No channel-pattern matching needed.

#### Terminology

| Term | Description |
|------|-------------|
| **switch-source** | Where the notification originated (tmux, wezterm, slack, etc.) |
| **current-env** | Where lemonaid TUI is currently running |
| **switch-handler** | Knows how to switch to a notification from a specific switch-source |

#### Handler Types

1. **Built-in handlers** (`tmux`, `wezterm`)
   - Enabled by default
   - Only work when `current-env == switch-source`
   - Can't switch to a tmux pane from wezterm (different process hierarchies)
   - Can be disabled: `tmux = false`

2. **Custom handlers** (e.g., `slack = "~/.config/lemonaid/handlers/slack.sh"`)
   - Always enabled regardless of current-env
   - Assumed to know how to switch across environments (e.g., open Slack app via URL scheme)

#### Proposed Config Syntax

```toml
[switch-handlers]
# Built-ins are enabled by default, can disable:
# tmux = false
# wezterm = false

# Custom handlers for other switch-sources:
slack = "~/.config/lemonaid/handlers/slack-open.sh"
```

#### Actionability

A notification is **Actionable** (can be switched to) if:
1. Its `switch-source` has a registered switch-handler, AND
2. Either:
   - The handler is a custom handler (always actionable), OR
   - The handler is built-in AND `current-env == switch-source` AND pane still exists

The TUI should indicate non-actionable rows (dimmed, filtered, or with a status message).

### Rejected Alternatives

#### MxN Handler Mapping

We considered allowing multiple handlers per notification (e.g., exec + switch):

```toml
# Rejected syntax
"claude:*" = ["exec:notify-send 'Switching'", "tmux"]
```

This was rejected because:
- Adds config complexity (`str | dict | list` syntax is awkward)
- Most notifications have one logical action
- Side-effects like logging are better handled via hooks

#### Channel-Pattern Matching

The current `"claude:*" = "tmux"` pattern matching is redundant - the notification already knows its switch-source.

#### exec: as Peer Handler

Treating exec commands as peer handlers conflates:
- **Switching** - the primary action (navigate to the notification source)
- **Side-effects** - logging, webhooks, desktop notifications

These should be separate config sections.

### Future: Hooks for Side-Effects

Side-effects should be a separate concept from switching:

```toml
[hooks]
before_switch = ["exec:log-switch.sh"]
after_switch = []
```

### Dream Use Case: Unified Notification Inbox

Imagine capturing notifications from multiple sources:
- Claude Code (via hooks) - switch-source: tmux/wezterm
- Slack (via Hammerspoon or API) - switch-source: slack
- Email (via IMAP listener) - switch-source: email

Each notification carries metadata about how to "return" to it:
- tmux: TTY, pane ID
- wezterm: workspace, pane ID
- slack: `slack://channel?team=T123&id=C456`
- email: message ID for `open mailto:...` or Mail.app URL scheme

The switch-handler for each source knows how to use that metadata.

#### Slack Notification Capture (Hypothetical)

Possible approaches:
- **Hammerspoon** (macOS): Watch notification center, extract Slack metadata
- **Slack API**: Poll or websocket for messages (requires auth)
- **Slack URL scheme**: `slack://channel?team=T123&id=C456` opens specific channel

A Slack switch-handler would be something like:
```bash
#!/bin/bash
# ~/.config/lemonaid/handlers/slack-open.sh
# Receives notification JSON on stdin
URL=$(jq -r '.metadata.slack_url' -)
open "$URL"
```

### Implementation Phases

1. [x] **Documentation** - Capture design thinking
2. [x] **Rename and simplify** - `terminal_env` → `switch_source`, auto-select handler
3. [x] **Actionability check** - Verify pane exists before marking as actionable
4. [ ] **Custom handlers** - Support external scripts for non-terminal sources

## app.py Is Too Big

`inbox/tui/app.py` has grown well past 900 lines. It owns table setup, refresh logic, history mode, resume command building, keybinding wiring, patch checking, column stretching, and all the action handlers. This is a sign of coupling — the file is the junction point where every feature lands because there's no separation between the TUI shell and the domain logic it orchestrates.

Splitting opportunities:
- **`_build_resume_command`** belongs in a backend registry (see below), not the TUI
- **History mode** (refresh, filter, resume) could be its own module or Screen
- **Column/table setup** and `_stretch_columns` could be extracted to a table helpers module
- **Patch checking** is Claude-specific and could live closer to `claude/patcher.py`

This is related to both the Backend Plugin Architecture and the general principle that the TUI should be a thin shell dispatching to domain logic.

## Backend Plugin Architecture

### The Problem

Backend-specific knowledge (claude, codex, openclaw) is leaking into generic code. `_build_resume_command` in `app.py` dispatches on channel prefix with hardcoded branches. Similar patterns exist in the watcher layer and notification handling. Every new backend means touching multiple generic modules.

### Direction

Channel prefixes (`claude:`, `codex:`, `openclaw:`) are the natural dispatch key. Each backend should register capabilities against its prefix:

- **`build_resume_argv(metadata) -> list[str]`** — how to resume a session
- **`parse_transcript_activity(entry) -> str | None`** — extract live activity description
- **`detect_turn_complete(entry) -> bool`** — whether the agent finished and is waiting

The TUI and watcher work against these interfaces. Adding a new backend means dropping a module into the right place and registering its prefix — no changes to `app.py` or watcher core.

### Current State

- `openclaw/utils.py` already has `build_resume_argv(metadata)` — extracted as first step
- claude/codex resume commands are still inline in `app.py` (one-liners, but still hardcoded)
- Watcher backends are already somewhat separated (`claude/watcher.py`, `codex/watcher.py`, `openclaw/watcher.py`) but share no formal interface

### Next Steps

1. [ ] Define a `Backend` protocol/registry keyed by channel prefix
2. [ ] Move claude/codex resume logic into their respective modules
3. [ ] Unify watcher backends behind a common interface
4. [ ] TUI dispatches via registry lookup instead of `if channel.startswith(...)` chains

## Customizable TUI Columns

Users should be able to configure column order, visibility, and sizing in `config.toml`. The current layout (Time, Name, Branch, CWD, Message, TTY) works for most cases, but power users may want to hide TTY, reorder columns, or adjust flex weights. Something like:

```toml
[tui.columns]
order = ["time", "name", "branch", "cwd", "message"]
# Each column can specify base width and flex weight
[tui.columns.name]
width = 14
flex = 0.10
[tui.columns.message]
width = 25
flex = 0.50
```

Keep the current hardcoded layout as the default — this is a nice-to-have, not urgent.

## OpenClaw Auto-Discovery

### The Problem

Every time you start a new OpenClaw session, you have to remember to run `!lemonaid openclaw register` from the TUI. This is easy to forget, and the session is invisible to lemonaid until you do.

### Direction

The watcher could periodically scan for new/active sessions and auto-register them. For remote hosts this means SSHing to check for recently-modified session files. The challenge is associating a discovered session with the correct local TTY/pane — without the `!` command running as a child of the TUI process, there's no way to walk the process tree to find the TTY.

Possible approaches:
- **Polling remote for new sessions**: Watcher SSHes periodically (e.g., every 30s) to `ls -t` session files, auto-registers any that are newer than the last check. TTY would be unknown — relies on cwd-based pane matching or manual `!lreg` to add TTY later.
- **OpenClaw hook on the gateway**: A hook fires on `agent:bootstrap` or session start, pushes a notification to lemonaid (via SSH back to local, or a webhook). Still no TTY.
- **Filesystem watch on remote**: `inotifywait` or similar on the remote, triggers registration. Overkill for now.

The TTY problem is the main blocker for a fully automatic experience. Without it, auto-discovered sessions can't be switched to via tmux — they'd show up in the non-switchable section until manually registered with `!lreg`.
