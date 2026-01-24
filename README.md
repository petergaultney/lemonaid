# 🍋🥤 lemonaid

Attention inbox for managing notifications from lemons (go on, say LLMs three times fast)
when you live in the CLI.

<img width="1186" height="386" alt="Screenshot 2026-01-22 at 21 36 45" src="https://github.com/user-attachments/assets/cff462af-52dc-4d61-a8ef-0a6949f87d30" />

Eventually other tools will get packaged here as well.

## Features

- **Notification inbox**: Track which [Claude Code](docs/claude.md) and [Codex CLI](docs/codex.md) sessions need your attention
- **Terminal integration**: Hit enter to jump directly to the waiting session's pane (supports [tmux](docs/tmux.md) and [WezTerm](docs/wezterm.md))
- **Scratch pane** (tmux): Toggle an always-on inbox with a keybinding - no startup delay, auto-hides after selection
- **Back navigation**: Toggle between your inbox and the session you jumped to
- **Auto-refresh TUI**: See new notifications appear without losing your place
- **Upsert behavior**: Repeated notifications update timestamp instead of creating duplicates
- **tmux session templates**: Spin up new Claude workspaces with a predefined window layout

## Installation

```bash
# Install globally with uv
uv tool install --editable ~/play/lemonaid

# For development
cd ~/play/lemonaid
uv sync
uv run pre-commit install
```

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
| `g` | Refresh |
| `q` / `Escape` | Quit |

### Programmatic Access

For JSON output and programmatic access (useful for lemons), see [docs/for-lemons.md](docs/for-lemons.md).

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

## Terminal Setup

- **tmux**: See [docs/tmux.md](docs/tmux.md) for pane switching, back navigation, session templates, and window colors
- **WezTerm**: See [docs/wezterm.md](docs/wezterm.md) for workspace/pane switching setup

## Configuration

Config file: `~/.config/lemonaid/config.toml`

```toml
[handlers]
# Map channel patterns to handlers
"claude:*" = "tmux"  # or "wezterm"
"codex:*" = "tmux"
```

See the terminal-specific docs for additional configuration options.

## Architecture

- **inbox**: SQLite-backed notification storage with Textual TUI
- **handlers**: Pluggable system for handling notifications (tmux, wezterm, exec)
- **claude**: Claude Code hook integration with transcript watching
- **codex**: Codex CLI hook integration with session watching
