# Lemonaid Feature Ideas

## Tmux "mark as read" keybinding (2026-01-20)

Add ability to mark notifications as read directly from tmux without opening lemonaid UI.

**Concept:** Bind a tmux key that marks the current pane's notifications as read.

**Implementation:**
1. Add CLI command: `lemonaid mark-read --tty /dev/ttys005`
2. Tmux keybinding: `bind-key m run-shell 'lemonaid mark-read --tty "#{pane_tty}"'`

**SQL query** (handles tty reuse edge case):
```sql
UPDATE notifications
SET read = 1
WHERE tty = ?
  AND unread = 1
  AND created_at > datetime('now', '-5 minutes')
```

The 5-minute window handles the edge case where a tty was reused for a different session - we only mark recent notifications from that tty as read.
