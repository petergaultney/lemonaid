# 🍋🥤 lemonaid

Monitor progress of and switch between lemons (go on... say 'LLMs' three times fast)
running in the terminal.

<img width="899" height="511" alt="The lemonaid inbox as a top strip, one row per session, above a Claude Code session" src="https://github.com/user-attachments/assets/bdb98206-b0f3-44e9-a395-541130edb2b9" />

## An inbox that stays in view

The inbox can live in a pane that follows you across every window and session
switch, so it is ambient rather than something you summon:

```bash
lemonaid tmux scratch --follow          # left or top, from config
lemonaid tmux scratch --flip            # move it to the other edge
```

Above, as a top strip, it draws the columns. On the left it has no room for
them, so each session becomes a card instead - name, then time, cwd and branch,
then the message wrapped over as many lines as the pane can spare:

<img width="899" height="511" alt="The inbox as a left sidebar, cards for each session, beside a Claude Code session" src="https://github.com/user-attachments/assets/9b82c2df-abf3-40ef-a529-f0e95a110abb" />

The bar above the list turns the unread marker's colour while something is
waiting for you. `prefix+l` toggles focus between the inbox and your work; `q`
parks it until you want it back.

To see it with invented sessions before wiring up your own:

```bash
uv run scripts/demo-inbox.py            # a throwaway tmux server, own inbox
uv run scripts/demo-inbox.py --kill
```

Full setup, keybindings, and behaviour: [docs/tmux.md](docs/tmux.md).

## How It Works

Lemonaid has two parts: **hooks** that fire when your lemons need attention, and a **TUI** (`lma`) that shows what's going on and lets you jump to sessions.

1. You add hooks to Claude Code, Codex CLI, and/or OpenCode (see [Integrations](#-integrations) below)
2. When a session stops or needs input, the hook writes a notification to a local SQLite database
3. The `lma` TUI displays active notifications, watches transcripts for live activity, and auto-archives sessions when they end
4. When you select an active session, you are taken directly to that pane/tab in `tmux`/WezTerm
5. Over time, archived sessions accumulate into a searchable **session history** — press `h` to browse past sessions across all projects and resume them

The TUI doesn't need to be running for notifications to arrive (hooks write directly to the DB), but it does need to run for live activity updates and automatic archiving.

## Features

- **Notification inbox**: Track which [Claude Code](docs/claude.md), [Codex CLI](docs/codex.md), [OpenClaw](docs/openclaw.md), and [OpenCode](docs/opencode.md) sessions need your attention, and what they're doing as they do it
- **Terminal integration**: Hit enter to jump directly to the waiting session's pane (supports [`tmux`](docs/tmux.md) and [WezTerm](docs/wezterm.md)). If the session has since died, its pane is recreated in the same directory rather than the jump failing
- **Session history & resume**: Browse archived sessions across all projects, filter by name/cwd/branch, and resume directly or copy the command
- **[Places](docs/places.md)**: Spin up a directory and its session in one command, and tear both down in one command. What "spin up a directory" means is a shell command you configure per repo, so worktrees (or whatever else you use) stay out of lemonaid's model
- **Snooze**: Hold a session that needs attention "but not yet" until a time you pick, with a snoozed list so nothing goes missing
- **Undo**: Reverse an accidental archive, mark-read, snooze, or rename - multi-level, with a toast naming what changed
- **Bootstrap**: `lemonaid claude bootstrap` imports historical Claude sessions from before lemonaid was installed into the archive
- **Always-visible sidebar** (`tmux`): [Follow mode](docs/tmux.md#follow-mode) keeps the inbox in view across every window and session switch, on the left or across the top. Sessions render as cards when the pane is too narrow for columns. Without follow mode it is still a scratch pane you toggle with a keybinding, with no startup delay
- **Auto-refresh TUI**: See new notifications appear without losing your place

### Assorted helpers
- **Claude statusline**: Colorful statusline showing time, elapsed, git branch, context %, vim mode
- **`tmux` session templates**: Spin up new named workspaces with a predefined window layout
- **`tmux` window status formatting**: An optional `tmux` integration to keep your status bar sane

## Installation

```bash
git clone https://github.com/petergaultney/lemonaid.git
cd lemonaid

# Install globally with uv
uv tool install --editable .

# For development
uv sync
uv run pre-commit install
```

## 🍋 Integrations

### Claude Code

Add hooks to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "lemonaid claude submit" }] }],
    "Stop": [{ "hooks": [{ "type": "command", "command": "lemonaid claude notify" }] }],
    "Notification": [{ "matcher": "permission_prompt", "hooks": [{ "type": "command", "command": "lemonaid claude notify" }] }]
  }
}
```

Features: sessions appear in the inbox the moment a prompt is submitted (`UserPromptSubmit`), auto-dismiss via transcript watching, live activity updates, binary patch for faster notifications.

**Full documentation**: [docs/claude.md](docs/claude.md) | [Binary patch](docs/claude-patch.md)

### Codex CLI

Add to `~/.codex/config.toml` **at the very top** (before any `[table]` headers):

```toml
notify = ["lemonaid", "codex", "notify"]
```

Features: auto-dismiss via session watching, live activity updates.

**Full documentation**: [docs/codex.md](docs/codex.md)

### OpenClaw

Register from within an OpenClaw TUI session:

```
!lemonaid openclaw register
```

Features: turn-complete detection, live activity updates, auto-dismiss on user input.

**Full documentation**: [docs/openclaw.md](docs/openclaw.md)

### OpenCode

Add this plugin at `~/.config/opencode/plugins/lemonaid.js` (or `.opencode/plugins/lemonaid.js` in a project):

```javascript
export const LemonaidPlugin = async ({ $ }) => ({
  event: async ({ event }) => {
    if (event.type === "session.idle" || event.type === "permission.asked") {
      await $`lemonaid opencode notify ${JSON.stringify(event)}`
    }
  },
})
```

Features: idle/permission notifications via plugin hooks, auto-dismiss via session DB watching, live activity updates.

**Full documentation**: [docs/opencode.md](docs/opencode.md)

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
| `m` / `M` | Mark as read / unread |
| `a` | Archive (remove from list) |
| `s` / `S` | Snooze session / list snoozed |
| `p` | Pin session to a place in the list, or unpin it |
| `Shift`+`↑`/`↓` | Move a pinned session up or down one slot |
| `z` | Undo the last inbox change |
| `r` | Rename session (clear to revert to auto-name) |
| `h` | Toggle session history |
| `c` | Copy resume command (in history mode) |
| `/` | Filter history |
| `f` | Move the scratch pane between top and left |
| `H` | Save scratch pane size (follow mode, once it has drifted) |
| `g` | Refresh |
| `?` | Show the key reference |
| `q` / `Escape` | Quit |

All keybindings are configurable. See [docs/keybindings.md](docs/keybindings.md).

### Programmatic Access

For JSON output and programmatic access (useful for lemons), see [docs/for-lemons.md](docs/for-lemons.md)
— or run `lemonaid for-lemons`, which prints the same guide from any install.

## Configuration

Config file: `~/.config/lemonaid/config.toml` — see [docs/config.md](docs/config.md) for the full reference.

- [docs/keybindings.md](docs/keybindings.md) - Customize TUI keybindings
- [docs/tmux.md](docs/tmux.md) - tmux integration and session templates
- [docs/wezterm.md](docs/wezterm.md) - WezTerm integration

## Architecture

- **inbox**: SQLite-backed session status storage with [Textual](https://textual.textualize.io/) TUI
- **claude**: Claude Code hook integration with transcript watching
- **codex**: Codex CLI hook integration with session watching
- **openclaw**: OpenClaw integration with turn-complete detection
- **opencode**: OpenCode integration with plugin events and live activity watching
