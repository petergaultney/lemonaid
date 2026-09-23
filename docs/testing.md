# Testing

Run the test suite with:

```bash
uv run pytest
```

## Watcher isolation is a safety invariant

Mounting `LemonaidApp` starts a background watcher that can update and archive
inbox rows. Tests isolate it with a temporary database and a nonexistent tmux
server. The watcher **must be stopped and joined before those test fixtures are
torn down**. Otherwise it can continue running with test tmux state after the
database path has reverted, and archive sessions in the developer's real
inbox.

`LemonaidApp.on_unmount` owns that shutdown. An autouse fixture also fails the
originating test if any watcher thread escapes, stopping it while the isolated
database and tmux environment are still in place.

Do not work around a leaked-watcher failure by weakening an assertion, stubbing
archive writes, or resetting watcher globals. Fix the lifecycle that leaked the
thread. Any test that starts a watcher directly must stop it before returning.

## Auditing automatic archives

Every watcher decision to archive a session is logged to `/tmp/lemonaid.log`
as an `auto-archive` event. The event includes the channel, reason, session ID,
TTY, terminal source, tmux socket, working directory, creation time, and the
evidence specific to the decision. For example:

```bash
rg 'auto-archive' /tmp/lemonaid.log
```

These records distinguish a missing pane, an exited process, and an older
session displaced by a newer session on the same TTY.
