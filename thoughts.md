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

## Session exit detection (2026-01-23)

Detect when a Claude session has exited and mark it as `<inactive>` in lma.

**Why:** Currently sessions stay in the list forever until manually archived. Showing inactive sessions differently would help users know which ones are still alive.

**Possible approaches:**
1. Check transcript file mtime - if no changes in X minutes, session is probably inactive
2. Look for specific transcript entries (e.g., `type=summary` appears at end of some sessions)
3. Check if the TTY is still valid / process still running
4. Look for an explicit "session ended" entry (unclear if Claude writes one)

**Implementation ideas:**
- Watcher already polls transcripts - could check for staleness
- Add a new status like "inactive" alongside unread/read/archived
- Could auto-archive after being inactive for a while

**Deferred:** Implementing after real-time message updates are working.
