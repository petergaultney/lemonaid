# Patch

- Ignore Codex automatic recap notifications before they can create inbox rows. Repair existing duplicate ungrouped rows while preserving brief attachments and waiters.
- Resolve Codex watcher startup, subscriptions, cursors, inbox delivery and stop hooks through the attached channel, so reconciled lemons can rearm their unified watcher.
- Allow lemon doctor to import on Python 3.11 without requiring the UI to have been imported first.
- Resolve subscribed Codex briefs before their first turn-complete notification, and restore missing unified watchers automatically during inbox refresh so a failed rearm does not leave them deaf.
- Find Codex notifications by their thread's saved rollout, independent of the terminal or multiplexer.
- Repair existing Codex pane locations at startup, during refresh and before switching, and find recorded panes when later hooks omit their TTY. Jump logs now include the attached clients' panes immediately after the switch.
