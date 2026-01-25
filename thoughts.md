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

1. **Documentation** (current) - Capture design thinking
2. **Rename and simplify** - `terminal_env` → `switch_source`, auto-select handler
3. **Actionability check** - Verify pane exists before marking as actionable
4. **Custom handlers** - Support external scripts for non-terminal sources
