# Recovering lemons and the inbox

When many processes die at once, such as a `pkill -f` that matched too much or a machine restart, most lemons recover on their own or need only their waiters rearmed. This guide covers how to tell which, and how to repair the inbox database by hand where no command does it. After a tmux restart specifically, see [Surviving a crash](tmux.md#surviving-a-crash).

## Find the lemons that need help

```bash
lemonaid lemon doctor --all
```

It lists lemons that are `deaf` (alive, but with no inbox waiter, so a `tell` to them won't be read) or `dead` (the harness exited). Its facts and their limits are in [for-lemons](for-lemons.md#checking-on-lemons-lemon-doctor). `lemonaid tell` also exits 1 when the recipient won't read the message, and logs it to `dead-letters.jsonl` in the inbox root.

`doctor` does not compare a brief's `## Waiters` with the waiters actually running, or look for a frozen terminal. For a lemon it calls healthy but that has gone quiet:

1. **Waiters:** for each `lemonaid watch ... --wait X` line in `## Waiters`, look for it in `ps -axww`. Paths can contain spaces, so match the whole string and not its first word.
2. **Frozen input:** `tmux capture-pane -p -t <pane>` shows text sitting after the prompt with no activity. A healthy idle lemon has an empty prompt. Find the pane in the lemon's inbox metadata (`tmux_pane_identity`); a brief's recorded tmux window goes stale when windows are renumbered.
3. **Unsaved work:** `git status` and `git log @{u}..` in its directory, before resuming it.

Don't trust `pane_current_command`. Claude Code titles itself with its version, and a shell wrapper such as `fish -c ...; exec fish` shows the shell over a live harness. A killed harness leaves a shell prompt whose last status is 143 (SIGTERM) and, for Claude, a `claude --resume <id>` line in the scrollback.

## Bring them back

- **A lemon with missing waiters:** `lemonaid tell <lemon> "rearm the waiters in your brief"`. A Claude lemon reads it only if its inbox waiter is armed; otherwise resume it.
- **A dead lemon:** `lemonaid lemon resume <lemon>`.
- **A dead Claude, by hand:** `claude --resume <id> "<prompt>"` with a prompt telling it to rearm its waiters. A session that ended in the middle of a tool call can refuse to resume without one.
- **A dead Codex, by hand:** `codex --no-daemon resume <id>`.
- **A dead lemon with uncommitted or unpushed work:** decide yourself whether to resume it; a script shouldn't.

Stop a waiter with `lemonaid watch stop --self`. Never kill waiters by pattern: `pkill -f watch` stops every lemon's matching waiters, not only yours.

## Repair the database by hand

Use a command where one exists. For a brief attached to the wrong lemon, see [A brief attached to the wrong thread](hq.md#a-brief-attached-to-the-wrong-thread); for a Codex session with no tty, see [Codex through the shared daemon](hq.md#codex-through-the-shared-daemon). For the rest, the database is `~/.local/share/lemonaid/lemonaid.db` (`LEMONAID_DB` replaces it). Copy it to a dated `.bak-` file first, and open it with `sqlite3 -cmd ".timeout 5000"` so a busy `lma` doesn't make the write fail.

- **An archived lemon is missing from the inbox but still running.** Archiving hides a row even when its lemon is alive and pinned. Pressing `z` in the same `lma` session undoes it; later, set the lemon's newest row back:

  ```sql
  update notifications set status = 'read'
  where id = (select max(id) from notifications where channel = '<channel>')
    and status = 'archived';
  ```

- **A deleted group.** Membership lives in `lemon_group_members` (`group_id`, `lemon_id`), and each member brief's `Groups:` line carries it too. Recreate it with `lemonaid group create <name>` and `lemonaid group add <name> <lemon-id>`. A backup of the database lists who was in it. Leave out archived lemons, or the group comes back full of dead rows.
- **A pin.** `pins` holds one row per channel with its position, and survives archiving. A lemon resumed on a new channel needs a new pin.
- **Two lemons with the same ID.** `lemonaid brief id --channel <channel> --reroll` picks a new name for one and keeps the old one as an alias.
