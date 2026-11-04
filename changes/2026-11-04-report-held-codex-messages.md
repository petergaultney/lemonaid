# Patch

#### Fixed

- **`tell` says when Codex holds a Codex lemon's messages and starts no turn from them.** `codex queue` exits 0 for any stored thread, so a message queued after an Esc interrupt waited for the next user prompt while `tell` said `listening`. lemonaid now reads a private copy of Codex's queue database, and a message that has waited a minute on an idle thread makes the lemon `parked`: `tell` exits 1 and says why, `lma` marks it `deaf`, and its parent wakes once.
- **`docs/codex.md` says what `daemon_auto_start = false` does.** It stops a Codex launch from starting the daemon, not from joining one that runs. Only `codex --no-daemon` keeps a launch off it.
