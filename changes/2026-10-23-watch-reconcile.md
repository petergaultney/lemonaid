# Minor

#### Added

- **`lemonaid watch reconcile` starts, replaces or restarts push scouts in one pass, so every live lemon that needs a scout has one.** After an install, commands start a pass in the background until one completes, and lemonaid schedules nothing else; the docs show how to run it from launchd or systemd. `[watch] reconcile = false` turns it off.

#### Fixed

- **A Claude lemon's push scout started by a Codex lemon now watches the Claude lemon.** A scout started from a Codex process, as `lemonaid tell` does for its recipient, took the caller's `CODEX_THREAD_ID` over its own `--channel`.
- **The inbox no longer starts a scout for a Codex lemon whose brief is `done`.**
