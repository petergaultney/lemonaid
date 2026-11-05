---
type: Notes
created: { at: 2026-11-05T12:00:04-05:00, by: VenueSki }
responsible-parties:
  - Peter Gaultney
contributors:
  - VenueSki
---
# Move a lemon to another place

`lemonaid lemon move <lemon> <destination>` moves a live Claude or Codex lemon into
another place. It stops the harness, then resumes the same conversation (Claude session,
Codex thread) in the destination directory, in that place's workspace. The lemon keeps
its Lemon-ID, brief, parent, groups and subscriptions.

```sh
lemonaid lemon move review-thing.GooseMud feat/eval-fixes --dry-run
lemonaid lemon move review-thing.GooseMud feat/eval-fixes
lemonaid lemon move review-thing.GooseMud ~/scratch/elsewhere
lemonaid lemon move --status <operation-id> --json
```

## The destination

A destination that starts with `/`, `~` or `.` is an existing directory. Anything else
is a place key in the lemon's own root, or in `--root`. A missing key is acquired through
the root's `create` and `path_of` hooks, as `place acquire` does; `--dry-run` acquires
nothing and refuses a key that doesn't exist yet.

In tmux, the lemon joins the session that already has a pane in the destination
directory. Protected sessions don't count, and several such sessions refuse the move. With
none, a new session is created there, named as `place open` would name it, with a shell
window. In WezTerm, the lemon opens in a workspace named for the key or directory. In cmux,
it opens in a new workspace.

## What happens

The command checks the move, then hands it to a detached worker and prints an operation
ID, so a lemon can move itself. A lemon moving itself is mid-turn and needs `--force`.

1. Recheck the native process, its terminal and the resume command.
2. Create the destination tmux session if needed.
3. Stop the harness with SIGTERM and stop its registered waiters, as `lemon restart` does.
4. Record the destination as the lemon's directory and workspace, then resume the session
   there through the terminal's own start, in a new window or tab, on a prompt saying where
   it now is.
5. Wait up to 30 seconds for a hook to report the new process, then record its terminal.
6. Close the old tmux pane when only its shell is left there.

Closing the old pane closes its window, and closes the old session when that was its last
pane. Clients attached to such a session switch to the destination session first, so none
is detached. A pane in a protected session (`protected_sessions` under `[places]`) always
stays open, even when the harness was its only process. A pane still running other jobs stays open, and so does every other window of
the old session: `place toss` closes those when you are done with them. In WezTerm and
cmux, the old tab stays open at its shell.

Delivery and autoresume hold off from the stop until the new process registers, as for a
restart. Both places are left with one purpose each, so a later `place toss` of either
works.

## Requirements

The same as for [`lemon restart`](lemon-restart.md#checks-before-stopping): a hook must
have recorded the session's process, and a Codex lemon needs a dedicated process
(`--no-daemon`) both now and in its configured resume command. A Codex resume always names
its directory with `--cd`, which Codex otherwise asks about when a session last worked
elsewhere. `lemonaid claude resume` resumes in the directory the lemon's inbox row records,
which the move changes first.

Claude has no flag to skip its folder-trust prompt, so a Claude lemon moves only into a
directory Claude already trusts: one where you accepted the prompt, or a directory below
one. lemonaid reads that from Claude's `.claude.json` and never writes it. To move into a
new directory, start Claude there once and accept the prompt first. A Codex resume is
started trusting its directory, as `lemon start` does.

The source lemon is stopped before its replacement starts because one conversation can't
run in two processes at once. Every check that can be made beforehand is made before the
stop.

## When it fails

- Before the stop, nothing changes and the status is `failed`.
- After the stop with nothing started, the status is `failed` and says the lemon is
  stopped. The lemon's row already names the destination, so `lemonaid lemon resume <lemon>`
  starts it there.
- When the resume started but no hook reported it in time, the status is `partial`. Look in
  the destination workspace: a startup dialog, such as Claude's folder trust in a directory
  it hasn't seen, stops a resume before its hooks run. The old pane stays open.
