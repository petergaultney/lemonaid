---
created-at: 2026-10-21T13:13:23-04:00
created-by: TwiceOld
---

# Patch

#### Fixed

- **`watch pr --wait` refuses to start beside the lemon's unified watcher.** It shares that watcher's cursors, so a `--once` waiter next to a push scout never woke: the scout reported each event first and marked it seen. The waiter still records itself in the brief, so the scout watches the PR.
