# Minor

#### Changed

- **Codex lemons get a push scout and no longer rearm `lemonaid watch --self`.** A detached scout queues each batch into the lemon's thread with `codex queue` and keeps watching until no Codex process has the thread open. The SessionStart and Stop hooks start it, and the inbox restarts it for any idle Codex lemon with a brief.
- **`lemonaid watch --self --codex-thread` beside a running scout prints `push scout running; nothing to rearm` and exits 0.** A lemon started with the old instructions spends one call on it instead of an error.
