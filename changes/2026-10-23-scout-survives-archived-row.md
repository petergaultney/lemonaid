# Patch

#### Fixed

- **A resumed lemon gets a push scout at once, instead of after its first turn.** The inbox archives a lemon's row when its process exits, and a scout treated that row as a detached brief and exited silently, so every scout started for a resumed Codex lemon died until its first turn ended. A scout now keeps watching while its Claude session or Codex thread runs, and a watcher that does exit at start says why on stderr.
