# Restart one lemon

`lemonaid lemon restart <lemon>` stops a live harness and runs its configured
resume command in the same tmux pane. Install the desired harness version first;
restart does not install packages.

```sh
lemonaid lemon restart my-task.TestyJob --dry-run --json
lemonaid lemon restart my-task.TestyJob
lemonaid lemon restart --status <operation-id> --json
```

The target is a Lemon-ID, channel, or attached brief name. The command returns an
operation ID after scheduling a detached worker, so a lemon can restart itself.
Self-restart normally needs `--force`, because its tool call is part of a turn.

## What resumes

Restart uses the same resume builder as restore and `lemon resume`, including the
backend's configured `resume_command`. For a direct Codex command, the shared
builder adds `--no-daemon` so restart retains a dedicated terminal process. The harness restores its conversation,
model, permissions and other native settings. Lemonaid does not reconstruct or
verify those settings, parse model displays, or replay the old process's flags
and environment. Put any required launch overrides in the configured resume
command or native configuration, as for an ordinary resume.

The command adds one initial instruction:

> You were just restarted in the same native session. Keep your existing task
> and brief. Rearm any watchers or other transient state you need to manage,
> read your pending inbox messages, and continue your existing work.

Both supported native harnesses accept that initial prompt through the existing
resume builder. The lemon rearms its own watcher and other transient state.
Restart does not infer subscriptions, start replacement scouts, or wait for a
model's acknowledgement. The stable Lemon-ID, brief attachment, groups and parent
remain attached to the existing native session.

## Checks before stopping

A normal SessionStart hook, Codex notification or Claude statusline must have
recorded the session's OS process identity. Install session hooks with
`lemonaid hooks install` and obtain a fresh observation for older sessions.
The identity records only PID, parent, start time, executable and terminal;
there is no new native-settings database or schema migration.

Restart checks the recorded tmux socket, pane, working directory and process
ancestry. It refuses dead or ambiguous targets, unrelated terminal jobs, changed
process generations, and launchers that remain alive after their harness exits. Shared Codex
app-server sessions cannot identify a dedicated process to stop; use a dedicated
launch/resume configuration (`--no-daemon`) for restartable Codex lemons.

Without `--force`, an observed busy turn or request for input refuses restart.
Draft text and arbitrary keystrokes are not inspected or preserved. Avoid typing
or starting tools during restart. `--force` permits an interrupted turn but never
overrides process or pane ownership checks.

## Stop, start and failures

A short reservation drains message delivery and excludes competing resume and
handoff operations. Messages sent during cutover remain pending. The worker
rechecks the source, sends SIGTERM to that exact process and waits up to ten
seconds; it never sends SIGKILL or signals a process group.

The harness owns shutdown of its tools and helpers. Lemonaid neither classifies
helper binaries nor kills descendant jobs. Before replacing the pane, it requires
all terminal processes to have exited except the captured root shell. A surviving
job prevents replacement. Detached or previously disowned jobs are not managed.
Old registered waiters are stopped, and the resumed lemon rearms them from the
instruction above. A SIGTERM timeout leaves the original watchers untouched.

`started` means the resumed process registered on the reserved pane. The short
reservation waits up to 15 seconds for that process ownership observation, so
autoresume cannot race native startup. It does not verify model or watcher readiness. Native startup failures appear in the
pane. The saved operation includes the command and its prompt environment.
A failure before launch retains the pane for inspection. There are no automatic
replacement retries and no second supervisor. An interrupted worker becomes
`partial` after its 90-second reservation expires; checking status or rerunning
the worker never repeats an uncertain signal or launch. Inspect the pane and use
the saved command/environment for manual recovery. Autoresume refuses a partial
restart until a fresh hook identifies a later live process for that session.

There is no batch mode.
