# Watching documents

`lemonaid watch doc` blocks until someone responds to a Markdown document through
Relay Comments (inline CriticMarkup blocks written by an Obsidian plugin), and
then wakes the lemon that wrote it. It uses no model turns while it waits: it reads the file
every 15 seconds.

```bash
lemonaid watch doc --wait <doc> --me "Author (MotorHoe)" --legacy Claude --once
lemonaid watch doc --wait <doc> --me "Reviewer (SaltyEbb)" --legacy Codex --codex-thread "$CODEX_THREAD_ID"
lemonaid watch doc --status <doc> --me "Author (MotorHoe)"
lemonaid watch openclaw start <doc> --session-key <openclaw session key>
lemonaid watch openclaw list
lemonaid watch openclaw stop <doc>
```

## Events

- **A thread needs a reply.** A thread is an optional `{==highlight==}` followed by
  `{{author="..." ...>>text<<}}` blocks with nothing between them. It is unanswered when its
  last block is not signed `--me` or one of the `--legacy` names. The waiter reports a thread
  when it becomes unanswered, and again when an unanswered thread gains a block.
- **The body changed** (only with `--edits`), once the text outside comment threads has been
  unchanged for `--quiet` seconds (45 by default).

Reported threads are remembered per document and `--me` name, so a waiter started later
reports only threads that are new or changed since.

## Waking the lemon

- **Claude Code:** run with `--once` as a background Bash task. It prints the first event and
  exits, and the task's completion wakes the session. Rearm after handling it.
- **Codex:** `--codex-thread <id>` queues the first event into that thread with `codex queue`
  and exits. The waiter needs to write `~/.codex`, so it runs outside the workspace sandbox;
  it refuses to start if it cannot.
- **OpenClaw:** `lemonaid watch openclaw start <doc> --session-key <key>` adds the doc to that
  session's watch list and starts one `systemd-run --user` unit per session if none is
  running. The unit runs `lemonaid watch doc --watch-list`, which runs one agent turn in the
  session for each event (`openclaw gateway call agent`) and keeps watching. Starting a doc
  for one session removes it from every other session's list. A doc leaves the list after 7
  days with no event (`--idle-days`), and the unit exits when its list is empty.

A delivery that fails is not recorded: a one-shot waiter exits 1 and the next waiter reports
the event again; a list waiter retries on its next read.

Only one waiter may run per document and `--me` name, and one per watch list. A second exits
with status 3, naming the first. `--status` exits 0 when a waiter is running and 1 when none
is.

## State

- Locks and reported threads: `$TMPDIR/watch-doc/` (`--state-dir` moves it). `$TMPDIR` is
  used because it is writable inside Codex's sandbox.
- OpenClaw watch lists: `~/.local/state/watch-doc/lists/` (`LEMONAID_WATCH_LISTS_DIR` moves
  it).

## Compatibility with the standalone `watch-doc.py`

This command replaces the `watch-doc` skill's `watch-doc.py` and `openclaw_watch.py`. The
flags are the same (`python3 watch-doc.py <args>` becomes `lemonaid watch doc <args>`), and
so are the state files, lock files, watch-list files, event text and wake messages. The two
can therefore run side by side during migration:

- A waiter started by either blocks a second one from the other for the same document and
  name, and `--status` from either reports it.
- A thread reported by one is not reported again by the other.
- An OpenClaw watch list is served by whichever waiter holds it; `start` from either
  launcher reuses a running waiter.

The one difference: `lemonaid watch openclaw start` has no `--watch-doc` flag. The unit it starts runs the same lemonaid as the launcher (`python -m lemonaid watch doc`), so there is no separate script path to choose.

Moving a caller over means changing the command it runs at its next rearm; no state needs to
be migrated. Waiters already running under the old script keep working until they exit.
