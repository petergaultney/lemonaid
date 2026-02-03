# 🍋🥤 lemonaid

Monitor progress of and switch between lemons (go on... say 'LLMs' three times fast)
running in the terminal.

<img width="998" height="184" alt="Screenshot 2026-01-24 at 6 34 01 PM" src="https://github.com/user-attachments/assets/75d591d6-1423-416a-a83f-3c3b668233ea" />

## Features

- **Notification inbox**: Track which [Claude Code](docs/claude.md) and [Codex CLI](docs/codex.md) sessions need your attention, and what they're doing as they do it
- **Terminal integration**: Hit enter to jump directly to the waiting session's pane (supports [`tmux`](docs/tmux.md) and [WezTerm](docs/wezterm.md))
- **Scratch pane** (`tmux`): Toggle an always-on inbox with a keybinding - no startup delay, auto-hides after selection
- **Auto-refresh TUI**: See new notifications appear without losing your place

### Assorted helpers
- **Claude statusline**: Colorful statusline showing time, elapsed, git branch, context %, vim mode
- **`tmux` session templates**: Spin up new Claude workspaces with a predefined window layout
- **`tmux` window status formatting**: An optional `tmux` integration to keep your status bar sane

## Installation

```bash
# Install globally with uv
uv tool install --editable ~/play/lemonaid

# For development
cd ~/play/lemonaid
uv sync
uv run pre-commit install
```

## 🍋 Integrations

### Claude Code

Add hooks to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [{ "hooks": [{ "type": "command", "command": "lemonaid claude notify" }] }],
    "Notification": [{ "matcher": "permission_prompt", "hooks": [{ "type": "command", "command": "lemonaid claude notify" }] }]
  }
}
```

Features: auto-dismiss via transcript watching, live activity updates, binary patch for faster notifications.

**Full documentation**: [docs/claude.md](docs/claude.md) | [Binary patch](docs/claude-patch.md)

### Codex CLI

Add to `~/.codex/config.toml` **at the very top** (before any `[table]` headers):

```toml
notify = ["lemonaid", "codex", "notify"]
```

Features: auto-dismiss via session watching, live activity updates.

**Full documentation**: [docs/codex.md](docs/codex.md)

### Slack (macOS)

Capture Slack notifications and deep-link directly to conversations:

```bash
# Install macOS dependencies
uv tool install --editable ~/play/lemonaid \
  --with pyobjc-framework-Quartz \
  --with pyobjc-framework-ApplicationServices

# Install the notification watcher daemon
lemonaid macos install-watcher

# Enable Slack in config
echo '[slack]' >> ~/.config/lemonaid/config.toml
```

When you select a Slack notification, lemonaid opens a `slack://` deep link directly to that channel/DM.

Deep linking requires a manually-exported mappings file with channel IDs. See [docs/macos.md](docs/macos.md) for the browser-based export process.

**Full documentation**: [docs/macos.md](docs/macos.md)

## Terminal Setup

- **`tmux`**: See [docs/tmux.md](docs/tmux.md) for pane switching, back navigation, session templates, and window colors
- **WezTerm**: See [docs/wezterm.md](docs/wezterm.md) for workspace/pane switching setup

## Usage

```bash
# Open the inbox TUI
lma

# Or via the full CLI
lemonaid inbox

# List notifications (non-interactive)
lemonaid inbox list
```

### TUI Keybindings

| Key | Action |
|-----|--------|
| `Enter` | Open notification (switches to that session) |
| `u` | Jump directly to earliest unread session |
| `m` | Mark as read |
| `a` | Archive (remove from list) |
| `r` | Rename session (clear to revert to auto-name) |
| `g` | Refresh |
| `q` / `Escape` | Quit |

All keybindings are configurable. See [docs/keybindings.md](docs/keybindings.md).

### Programmatic Access

For JSON output and programmatic access (useful for lemons), see [docs/for-lemons.md](docs/for-lemons.md).

## Configuration

Config file: `~/.config/lemonaid/config.toml`

- [docs/keybindings.md](docs/keybindings.md) - Customize TUI keybindings
- [docs/tmux.md](docs/tmux.md) - tmux-specific options
- [docs/wezterm.md](docs/wezterm.md) - WezTerm-specific options

## Data Locations

- **Database**: `~/.local/share/lemonaid/lemonaid.db`
- **Logs**: `~/.local/state/lemonaid/logs/`
- **Config**: `~/.config/lemonaid/config.toml`
- **Slack mappings**: `~/.local/state/lemonaid/slack-mappings.json`

## Architecture

- **inbox**: SQLite-backed notification storage with Textual TUI
- **handlers**: Auto-selects switch-handler based on notification's switch-source (tmux, wezterm, slack)
- **claude**: Claude Code hook integration with transcript watching
- **codex**: Codex CLI hook integration with session watching
- **macos**: Notification Center watcher daemon using Accessibility API
- **slack**: Deep linking to Slack channels/DMs via manually-exported channel mappings
