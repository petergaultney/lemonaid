---
name: watch-briefs
description: Wait at zero token cost for a direct child's brief Status or Needs ask to change, then read the changed briefs and act. Use when a parent lemon is waiting on its children.
---

# Watch children's briefs

Use `lemonaid watch briefs --children --self` to wait on direct children through
Lemonaid's Lemon-ID parent links. Grandchildren are their own parent's responsibility.
You need an attached brief to use `--self`; an explicit parent Lemon-ID, channel, or
brief name can replace it.

Check `lemonaid watch briefs --children --self --status` first. If a waiter is running,
keep it; a duplicate exits 3. An optional `--me "<watcher name>"` keeps independent
watchers apart. Use the same name for status checks and every rearm.

In Claude Code, start `lemonaid watch briefs --children --self --once` as a background
Bash task with `timeout: 2147483647`, then end the turn. Its completion wakes you. Rearm
after handling a batch, or if the harness stops the task at its background time limit.

In Codex, check that `CODEX_THREAD_ID` is set and `codex queue --help` succeeds. Start
`lemonaid watch briefs --children --self --codex-thread` as an escalated `exec_command`
session, then end the turn. The bare flag reads the thread ID from the environment;
`codex queue` needs access outside the workspace sandbox. A setup refusal means no
waiter started. The first batch queues a turn and exits.

The first run takes current children as its baseline. Rearms report transitions made
since the last successful delivery, plus newly linked children in a selected status,
without repeating delivered events. By default, only entry into `merge` or `done` wakes.
Repeat `--to STATUS` to choose other destination statuses, for example
`--to blocked --to done`. Needs-only changes never wake, even in a selected status.
Ignored changes still advance the saved state, so the next wake reports the latest
previous status. Progress edits stay quiet. Missing or unlinked briefs are ignored.
Changes are sampled every 5 seconds and delivered after 2 quiet seconds; `--interval`
and `--quiet` adjust these timings.

Target values must be known brief statuses. Each target set has independent state and
locks, regardless of argument order or duplicates. Omitting `--to` shares state with
explicit `--to merge --to done`. Use the same options for status checks and rearms.

When woken, read the named children's briefs and act on their current Status and asks.
Then rearm the same command. Do not replace this waiter with a polling loop or scheduled
wakeups. Record its exact command in your brief's `## Waiters`, and keep your status and
what you are waiting on current.

State and locks are separate from other watchers, under `$TMPDIR/lemonaid-watch-briefs/`.
`--state-dir` moves them. A failed delivery is not recorded, so a rearm retries it.
Stop your own waiter by its process ID when the child work no longer needs watching,
and remove its command from your brief. Do not delete shared lock files.
