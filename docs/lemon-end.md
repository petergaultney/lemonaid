---
type: Notes
created: { at: 2026-11-24T14:54:59-05:00, by: PruneKid }
responsible-parties:
  - Peter Gaultney
contributors:
  - PruneKid
---
# End one lemon

`lemonaid lemon end <lemon>` ends one lemon without tossing the place it shares with
others. It is meant for an author whose reviewers run in windows of its own session: end
each one once its PR merges, and keep working.

```sh
lemonaid lemon end FrownNag.review-lemonaid-592 --dry-run
lemonaid lemon end FrownNag.review-lemonaid-592 [--expect STATUS]...
lemonaid lemon end --status <operation-id> --json
```

The target is a Lemon-ID, channel, or brief name. Every form takes `--json`.

A lemon alone in its tmux session is usually the lemon of its own place, such as an
author working in a place of its own. Ending it would leave the session and directory behind, so the
merge event doesn't name it, and `lemon end` says that `lemonaid place toss <key>` ends
the place instead.

## The Status you expect

Anyone may end any lemon whose brief's Status is one they expect: `done` unless they pass
`--expect`, which they may repeat. `--expect none` matches a brief with no Status. Any
other Status is printed with what was expected, and nothing is done:

```text
FrownNag.review-lemonaid-592's Status is approve, not done
```

It doesn't wait for a turn in progress. SIGTERM cuts that turn short, as with
`lemon restart --force`, and its transcript keeps everything up to that point.

## The merge-time hint

When one of your PRs merges or closes, the event your watch delivers names each lemon
whose brief names you as `parent:`, that shares its tmux session with another live lemon,
and whose work is done: that PR is in its PRs table and all of them have merged or closed,
or its Status says `done`. Each gets the command that ends it. A lemon whose Status isn't
`done` yet gets `--expect` for its Status as it is now and for `done`, which a reviewer
often sets while it handles the same merge:

```text
PR #592 is now MERGED; FrownNag, which you started, is done: end it with `lemonaid lemon end FrownNag.review-lemonaid-592 --expect done --expect approve`
```

If its Status changes to anything else before you run it, `end` refuses and prints the new one.

`lemonaid brief children --self` lists every lemon whose brief names you as `parent:`,
even when its parent link names your own parent, each with its `lemon end` command and
whether its cleanup is ready.

## What it does

1. It reserves the lemon as `lemon restart` does, so messages, autoresume and the
   inbox watcher leave it alone while its harness stops. It checks again, then sends
   SIGTERM to the exact harness process a hook recorded and waits up to ten seconds.
   It never sends SIGKILL.
2. It archives the lemon's inbox card, stops its watcher, its push scout and every
   waiter it started by hand, and moves its brief and mailbox to the attic as the
   record, as `place toss` does. `lemon resume --recreate` can bring it back.
3. It closes the lemon's own pane once nothing, or only the shell the lemon started in,
   is left there. A window closes with its last pane. Other panes in the window stay.

The pane stays open, and the output says why, when other jobs still run in it, when
it is the last pane of its session (ending a session is `place toss`'s job), or when
its session is in `[places] protected_sessions`.

A lemon whose harness has already exited keeps its pane as it is; only its card,
waiters and brief are dealt with. Ending a lemon twice changes nothing the second time.

Afterwards the inbox no longer shows it, `brief children` leaves it out (`--all` still
lists it, with cleanup `cleaned`), and its parent's watch doesn't report it as gone.

## Checks before stopping

The same as for [`lemon restart`](lemon-restart.md#checks-before-stopping): a hook
must have recorded the harness's process, and that process must still own the pane
lemonaid recorded. If lemonaid can't tell which process to stop, it refuses and
changes nothing.

An interrupted end keeps the lemon reserved until its 90-second deadline, then shows as
`partial` in `--status`; inspect its pane before ending or resuming it again.
