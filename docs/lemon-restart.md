# Restart one lemon

`lemonaid lemon restart <lemon>` upgrades the running harness process by resuming
the same native conversation in the same tmux pane. Install the desired harness
version first. Restart does not install packages.

```sh
lemonaid lemon restart my-task.TestyJob --dry-run --json
lemonaid lemon restart my-task.TestyJob
lemonaid lemon restart --status <operation-id> --json
```

The target can be a Lemon-ID, channel, or attached brief name. The command returns
an operation ID after scheduling a detached coordinator, including when the
target calls it on itself. Use `--status` to inspect the saved phase, outcome,
error, and same-session recovery command. Status inspection never repeats a stop
or launch.

The native session ID, Lemon-ID, attached brief, inbox row, name, emoji, pin,
groups, parent, and snooze stay attached to that conversation. The pane stays in
its window without selecting it or changing the layout. Its replacement can have
a different TTY; fresh hook evidence updates the row's process and terminal data.

## Before restarting

Install Lemonaid's session hooks with `lemonaid hooks install`. A native
SessionStart, notification, or Claude statusline observation must have bound the
session to its current process generation. Restart refuses an older session
without that evidence. It requires a full native session ID, an existing native
transcript and working directory, a recorded tmux socket, and recoverable model
and operating settings.

Codex must run as a dedicated `--no-daemon` TUI. A shared or remote app-server is
refused. Configured resume commands must be simple native commands or the built-in
`lemonaid claude resume` wrapper. Other wrappers and unsupported operating flags
are refused before stopping anything. The built-in Claude wrapper is planned as
a direct native resume so it cannot change the verified working directory.

The live model display must corroborate the captured native model. A model
selection made after the last turn cannot silently become the previous model.
If the model display is hidden or cannot be interpreted, restart refuses.
Codex provider and reasoning effort must be recoverable from native turn context
or explicit configuration overrides. Existing extra writable directories and
permission flags are retained; restart does not add writable roots. Codex's temporary
per-process tool directory is regenerated rather than replayed from the old PATH.
The binding records both set and unset environment overrides, plus resolved native
home paths. Unset home overrides stay unset, preserving native default account/config
lookup; a caller's custom homes or provider selectors cannot leak into the restart.
An older incomplete environment binding requires a fresh native hook observation.

Claude requires a running push scout before restart. A missing scout or a harness-owned
background waiter is refused before quiescing, because detached coordination cannot
recreate a tool-owned waiter. Codex can restart with a missing watcher.
Busy turns, input requests, draft text, and unrecognized composer contents are
refused by default. `--force` allows interruption or discarded input, and prints
a warning about tools' external effects. It never overrides process ownership,
model, directory, or launch-setting checks. Other background jobs on the terminal or in the harness descendant tree
must finish first, including when using `--force`.

Known direct native helpers are checked by kernel executable path, launch arguments
and parent generation: Claude's sleep inhibitor and Codex's bundled code-mode host.
Their tool-job descendants remain subject to refusal, and surviving helpers must
exit before pane replacement. Restart does not adopt previously disowned OS jobs.

For a self-restart, `--force` is normally necessary because its tool call is part
of an active turn. A dead lemon uses `lemonaid lemon resume` instead.

## Cutover and failures

The operation reserves the channel, drains in-flight delivery, stops only its
registered waiters, and rechecks the native transcript and process generation.
It sends SIGTERM to that exact harness PID and waits up to ten seconds. It never
uses SIGKILL on the harness, types into its composer, or signals its process group.

Messages sent during cutover remain pending. Delivery, watcher startup, handoff,
automatic archive decisions, and explicit or automatic resume respect the
reservation. Only a replacement carrying its operation token can establish its
watcher during verification. Readiness requires the expected native session,
model, pane generation, and a fresh watcher. Claude's push scout must use the
replacement's socket. During verification, the resume prompt and session hook defer
tool use. Continuation instructions are queued for the rebuilt watcher and released
with pending messages after readiness, so tool approval cannot hide the model display
before verification.

Startup has a 60-second deadline. A replacement that exits after its generation
was captured can receive one recovery resume in the reserved pane, subject to
the autoresume crash-loop limit. A running replacement with failed verification
is left for inspection. SIGTERM timeout preserves the source and restores its
watcher, and records an error if that watcher cannot register. Unmanaged surviving jobs or a changed pane stop replacement.

A supervisor reconciles a coordinator that dies. Abandoned reservations also
reconcile on expiry without repeating uncertain signals or launches. A partial
operation retains its error and recovery command; inspect the pane before using
that command. Autoresume cannot start another harness when an interrupted restart
has no evidence of a later session registration.

The tool cannot undo external effects from an interrupted turn. Fresh transcript
checks and cooperative turn-start hooks reduce the interval in which user input
can race with a stop; arbitrary keystrokes cannot be made atomic with SIGTERM.
Restart does not preserve a shell job table or guarantee scrollback preservation.

There is no `--all` or batch mode in this version.
