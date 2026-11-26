# Patch

#### Fixed

- **An OpenClaw lemon gets one turn per burst of changes, not a queue of stale ones.** Its scout and `watch openclaw` doc waiter hold events while the session is mid-turn and deliver them together once it is idle, and a doc body change made during the lemon's turn no longer wakes it.

#### Changed

- **`watch openclaw start` signs as the lemon's Brief-ID name by default,** so `--me` is optional; it also takes `--legacy`.
