# Watching documents, PRs, and files

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
  exits, and the task's completion wakes the session. Rearm after handling it, and after the
  harness stops it at its background time limit
  ([Claude setup](claude.md#2-keep-background-waiters-running)).
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

## Watching a PR

`lemonaid watch pr` blocks until a GitHub PR changes, using one `gh api graphql` call per
`--interval` (60 seconds by default).

```bash
lemonaid watch pr --wait 90 --head <sha you handled> --comments --me "Author (MotorHoe)" --once
lemonaid watch pr --wait 90 --head <sha> --comments --me "Reviewer (SaltyEbb)" --codex-thread "$CODEX_THREAD_ID"
lemonaid watch pr --status 90 --me "Author (MotorHoe)"
```

It reports a push (the head differs from `--head`), a merge or close, a move to or from
draft, a review decision change, and with `--comments` a new human comment, a conflict with
the base, or failed CI. A comment
counts as human when it is in an unresolved, non-outdated review thread, a submitted
review's body, or the PR conversation, is not from a bot, and does not start with 🍋 (lemons
post with the human's account, so the marker is the only way to tell). Comments already
reported, and the last reported draft flag and decision, are kept per PR and `--me` in
`$TMPDIR/watch-pr/`, so a rearm reports what changed in between and nothing it already
reported. Pass the head you just handled as `--head` when rearming; without it the first
fetch is the baseline. `--repo owner/name` defaults to the current directory's repo. It
wakes Claude and Codex the same way `watch doc` does.

`--comments` is the author's mode, so only the author is woken for merge blockers:

- A conflict is reported once per head, when GitHub says `CONFLICTING` (`UNKNOWN`, while it
  computes, is not a conflict). A waiter armed on a PR that already conflicts reports it at
  once.
- Failed CI is reported once per head, after every check on it has finished. Required
  checks count when the PR has any; otherwise every check does.
- The heads reported are kept beside the other state, so a rearm on the same head is quiet
  and a new push that still conflicts or fails is reported.

## Watching files and directories

`lemonaid watch file` blocks until a file or directory changes. It wakes Claude and Codex
the same way the other watchers do.

```bash
lemonaid watch file --wait notes.md --me "Author (MotorHoe)" --once
lemonaid watch file --wait ~/some/inbox --wait other.md --me "Author (MotorHoe)" --codex-thread "$CODEX_THREAD_ID"
lemonaid watch file --status notes.md --me "Author (MotorHoe)"
```

- A file is reported when it is created, removed, or its contents change.
- A directory is reported when a regular file directly in it is added, removed, or
  rewritten. Hidden files and subdirectories are ignored, so a lock file or a `done/`
  folder does not wake anyone.
- A change is reported once it has been quiet for `--quiet` seconds (2 by default); paths
  are read every `--interval` seconds (5 by default).
- What was last reported is kept per set of paths and `--me` in
  `$TMPDIR/lemonaid-watch-file/`, so a rearmed waiter reports anything that changed in
  between. The first waiter for a set of paths takes their current state as its baseline.

## Compatibility with the standalone `watch-doc.py`

`lemonaid watch doc` replaces the `watch-doc` skill's `watch-doc.py` and
`openclaw_watch.py`, and `lemonaid watch pr` replaces the `watch-pr` skill's `watch-pr.py`.
The flags are the same (`python3 watch-doc.py <args>` becomes `lemonaid watch doc <args>`,
and `python3 watch-pr.py <args>` becomes `lemonaid watch pr <args>`), and so are the state
files, lock files, watch-list files, event text and wake messages. Old and new can
therefore run side by side during migration:

- A waiter started by either blocks a second one from the other for the same document or
  PR and name, and `--status` from either reports it.
- A thread or comment reported by one is not reported again by the other.
- An OpenClaw watch list is served by whichever waiter holds it; `start` from either
  launcher reuses a running waiter.

There are two differences. `--status` checks the lock without taking it, so it never makes a waiter that is starting at the same moment refuse to start, and a starting waiter retries for a second if something else is holding the lock for a moment. And `lemonaid watch openclaw start` has no `--watch-doc` flag. The unit it starts runs the same lemonaid as the launcher (`python -m lemonaid watch doc`), so there is no separate script path to choose.

Moving a caller over means changing the command it runs at its next rearm; no state needs to
be migrated. Waiters already running under the old script keep working until they exit.
