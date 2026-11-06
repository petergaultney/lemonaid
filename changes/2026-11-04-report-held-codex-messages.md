# Patch

#### Fixed

- **`tell` says when Codex holds a Codex lemon's messages and starts no turn from them.** A message that has waited a minute on an idle thread makes the lemon `parked`: `tell` exits 1 and says why, `lma` marks it `deaf`, and its parent wakes once.
- Codex's queue is queried read-only, without copying the database. Read failures, including incompatible schema changes, log a warning with the database path and error while held-message detection is skipped.
- **`docs/codex.md` says what `daemon_auto_start = false` does.** It stops a Codex launch from starting the daemon, not from joining one that runs; only `codex --no-daemon` keeps a launch off it.
