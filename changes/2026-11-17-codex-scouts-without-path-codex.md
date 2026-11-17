# Patch

#### Fixed

- **A Codex push scout delivers when the scout host's `codex` on `PATH` doesn't work.** It runs `codex queue` with the executable of the Codex process that has the thread open, and a failed `codex queue` puts its stderr in the log.
- **A push scout that keeps failing says so.** `watch --self --status` reports `push scout failing` with the reason, `tell` calls the lemon deaf with it, and the scout host waits longer before each retry, up to ten minutes, instead of every 30 seconds.
