---
name: watch-briefs
description: Wait at zero token cost for a direct child's brief Status or Needs ask to change, then read the changed briefs and act. Use when a parent lemon is waiting on its children.
---

# Watch children's briefs

With an attached brief, prefer `lemonaid watch --self` for child statuses alongside Watching, PRs, Docs and inbox messages.

<!-- harness: claude -->
Check `lemonaid watch --self --status`. If it says `push scout running`, lemonaid is watching for you and pushes each batch into your session, children's status changes included. Handle each batch as it arrives. If it says `no watcher running`, run `lemonaid watch --self --push`, which starts the scout and returns; only if that prints `not started`, run `lemonaid watch --self` as a background Bash task (`timeout: 2147483647`) and rearm it after each batch.
<!-- /harness -->

<!-- harness: codex -->
Check `lemonaid watch --self --status`. If it says `push scout running`, lemonaid is watching for you and queues each batch into your thread; handle each batch as it arrives. If it says `no watcher running`, run `lemonaid watch --self --push` with escalated permissions, which starts the scout and returns; only if that prints `not started`, run `lemonaid watch --self --codex-thread` in an escalated exec_command session and rearm it after each batch.
<!-- /harness -->

The standalone command below remains available.

Use `lemonaid watch briefs --children --self` to wait on direct children through
Lemonaid's Lemon-ID parent links. Grandchildren are their own parent's responsibility.
You need an attached brief to use `--self`; an explicit parent Lemon-ID, channel, or
brief name can replace it.

Check `lemonaid watch briefs --children --self --status` first. If a waiter is running,
keep it; a duplicate exits 3. An optional `--me "<watcher name>"` keeps independent
watchers apart. Use the same name for status checks and every rearm.

<!-- harness: claude -->
In Claude Code, start `lemonaid watch briefs --children --self --once` as a background
Bash task with `timeout: 2147483647`, then end the turn. Its completion wakes you. Rearm
after handling a batch, or if the harness stops the task at its background time limit.
<!-- /harness -->

<!-- harness: codex -->
In Codex, check that `CODEX_THREAD_ID` is set and `codex queue --help` succeeds. Start
`lemonaid watch briefs --children --self --codex-thread` as an escalated `exec_command`
session, then end the turn. The bare flag reads the thread ID from the environment;
`codex queue` needs access outside the workspace sandbox. A setup refusal means no
waiter started. The first batch queues a turn and exits.
<!-- /harness -->

The first run takes current children as its baseline and reports nothing already true, so check them yourself first (`lemonaid brief children --self`). Rearms report transitions made
since the last successful delivery, plus newly linked children in a selected status,
without repeating delivered events. By default, only entry into `merge` or `done` wakes.
Repeat `--to STATUS` to choose other destination statuses, for example
`--to blocked --to done`. Needs-only changes never wake, even in a selected status.
Ignored changes still advance the saved state, so the next wake reports the latest
previous status. Progress edits stay quiet. Missing or unlinked briefs are ignored.
Changes are sampled every 5 seconds and delivered after 2 quiet seconds; `--interval`
and `--quiet` adjust these timings.

Target values must be statuses a brief sets; `active` and `idle` are not, so they can't be targets. Each target set has independent state and
locks, regardless of argument order or duplicates. Omitting `--to` shares state with
explicit `--to merge --to done`. Use the same options for status checks and rearms.

When woken, read the named children's briefs and act on their current Status and asks.
Then rearm the same command. Do not replace this waiter with a polling loop or scheduled
wakeups. The command automatically records itself in an attached brief’s `## Watching`
and updates the entry on rearm. Recording uses the attached brief of the lemon the waiter wakes. Keep your status and
what you are waiting on current.

State and locks are the calling lemon's cursors, under `~/.local/state/lemonaid/cursors/`.
`--state-dir` moves them. A failed delivery is not recorded, so a rearm retries it.
Stop your own waiter with `lemonaid watch stop --self briefs` when the child work no longer
needs watching; it also removes the entry from your brief. Never `pkill -f` the waiter
command, which stops every lemon's matching waiter. Do not delete shared lock files.
