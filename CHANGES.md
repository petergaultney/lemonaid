# Changelog

## 0.3.0 (2026-01-24)

### Added

- **Real-time activity updates**: The message column now updates continuously as Claude works, showing the current tool being used (e.g., "Reading main.py", "Running pytest", "Searching for pattern"). Updates happen for all active sessions, not just unread ones.

### Changed

- Watcher now polls all active sessions (not just unread) to provide live activity feedback
- Separated "mark as read" from "update message" - marking happens on first activity, messages update continuously

## 0.2.3 (2026-01-23)

### Fixed

- Scratch pane window now named "lma" instead of hostname:lemonaid
- `lma` command now sets terminal title to "lma" (was missing, causing window status to show hostname)

## 0.2.2 (2026-01-23)

### Changed

- **Scratch mode**: `q`/`Escape` now hides the pane instead of quitting, keeping lma alive for instant re-toggle

## 0.2.1 (2026-01-23)

### Added

- **Jump to unread** (`u`): New keybinding to jump directly to the earliest unread session without navigating through the list

## 0.2.0 (2026-01-23)

### Added

- **Scratch pane**: Toggle a persistent `lma` pane with `lemonaid tmux scratch`. The pane stays running in the background for instant show/hide without startup delay. Auto-dismisses after selecting a notification.
- `lma --scratch` flag for running in scratch mode (auto-hide after selection)

## 0.1.1

### Added

- `tui.transparent` config option for terminal transparency support
- Notification names derived from tmux session name automatically

### Fixed

- Various tmux color improvements

## 0.1.0

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
