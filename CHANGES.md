## 0.4.10 (2026-01-26)

#### Fixed

- **Watcher restores transcript truth**: Watcher now caches transcript entry timestamps (not just message strings). On each poll, if the DB message differs from transcript but timestamp is unchanged, the watcher restores the DB to match transcript. Fixes "Permission needed" persisting when notify handler fired late and overwrote the watcher's message.

## 0.4.9 (2026-01-26)

#### Changed

- **Better watcher logging**: Log entry type and timestamp when marking notifications as read. Log existing state when upserting notifications. Helps debug permission prompt flapping.

## 0.4.8 (2026-01-26)

#### Fixed

- **Git worktree support**: Watcher now finds Claude session transcripts when working in git worktrees by searching parent directories for the Claude project path.
- **Encoding resilience**: Watcher no longer crashes on malformed UTF-8 in session files.

## 0.4.7 (2026-01-24)

#### Added

- **Configurable select key**: New `select` keybinding option (e.g., `select = "o"`) adds additional keys for selecting a session. Enter always works regardless of config.

## 0.4.6 (2026-01-24)

#### Changed

- **Smarter scratch pane toggle**: `prefix+l` now selects the scratch pane if it's visible but not focused, instead of hiding it. Press again when focused to hide. This makes the keybinding more idempotent - pressing it always gets you to the scratch pane.

## 0.4.5 (2026-01-24)

#### Added

- **Configurable keybindings**: All TUI keybindings can now be customized in `config.toml`. Each action can have multiple keys (e.g., `quit = "qQ"`), and arrow key alternatives can be set for up/down navigation (e.g., `up_down = "kj"` for vim-style).

## 0.4.4 (2026-01-24)

#### Added

- **Rename sessions from TUI**: Press `r` to rename any session directly in the inbox. Enter a custom name or clear to revert to auto-detected naming. Names persist and survive session updates.

#### Changed

- **TUI modularized**: Split monolithic `tui.py` into `tui/` package with separate modules for app, screens, and utilities.

## 0.4.3 (2026-01-24)

#### Added

- **Auto-archive on session exit**: Sessions are now automatically archived when the watcher detects the Claude/Codex process is no longer running on its TTY. No more stale sessions lingering in the inbox.

## 0.4.2 (2026-01-24)

#### Fixed

- **TUI startup speed**: Fixed ~2 second delay on TUI startup by moving Claude binary patch check to a background thread.

## 0.4.1 (2026-01-24)

#### Added

- **Claude statusline**: Optional `lemonaid-claude-statusline` command for Claude Code's `statusLine` setting. Shows time, elapsed since last message, git branch, context window usage (with color gradient), and vim mode.

#### Fixed

- **Scratch pane first-launch**: Fixed issue where the scratch pane required two key presses on first launch. The cause was `tmux new-session` changing the implicit "current pane" context; now we capture and explicitly target the original pane.

# 0.4.0 (2026-01-24)

#### Added

- **Codex support**: Notifications and live activity updates for Codex CLI sessions.
- Unit tests for shared watcher utilities and Codex watcher activity parsing.

#### Changed

- Consolidated Claude/Codex watcher logic into shared `lemon_watchers` utilities while keeping backend-specific code in their packages.

# 0.3.0 (2026-01-24)

#### Added

- **Real-time activity updates**: The message column now updates continuously as Claude works, showing the current tool being used (e.g., "Reading main.py", "Running pytest", "Searching for pattern"). Updates happen for all active sessions, not just unread ones.

#### Changed

- Watcher now polls all active sessions (not just unread) to provide live activity feedback
- Separated "mark as read" from "update message" - marking happens on first activity, messages update continuously

## 0.2.3 (2026-01-23)

#### Fixed

- Scratch pane window now named "lma" instead of hostname:lemonaid
- `lma` command now sets terminal title to "lma" (was missing, causing window status to show hostname)

## 0.2.2 (2026-01-23)

#### Changed

- **Scratch mode**: `q`/`Escape` now hides the pane instead of quitting, keeping lma alive for instant re-toggle

## 0.2.1 (2026-01-23)

#### Added

- **Jump to unread** (`u`): New keybinding to jump directly to the earliest unread session without navigating through the list

# 0.2.0 (2026-01-23)

#### Added

- **Scratch pane**: Toggle a persistent `lma` pane with `lemonaid tmux scratch`. The pane stays running in the background for instant show/hide without startup delay. Auto-dismisses after selecting a notification.
- `lma --scratch` flag for running in scratch mode (auto-hide after selection)

## 0.1.1

#### Added

- `tui.transparent` config option for terminal transparency support
- Notification names derived from tmux session name automatically

#### Fixed

- Various tmux color improvements

# 0.1.0

Initial release with core features:

- **Inbox TUI** (`lma`): View and manage notifications from Claude Code and other tools
- **Notification system**: Receive notifications via `lemonaid claude notify` hook
- **tmux integration**: Switch to notification source, back-navigation, session templates
- **WezTerm integration**: Alternative to tmux with similar features
- **Window status**: Colorized tmux window titles based on directory/process
- **Claude Code patcher**: Reduce notification delay from 10s to 100ms
- **Mark as read**: `prefix + m` keybinding for tmux
- **Unread indicators**: Visual distinction for unread notifications
- **Session templates**: Create tmux sessions with predefined window layouts
