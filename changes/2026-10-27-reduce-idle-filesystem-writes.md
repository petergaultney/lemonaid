---
type: Notes
created: { at: 2026-10-27T16:39:00-04:00, by: ChurnOdd }
responsible-parties:
  - Peter Gaultney
contributors:
  - ChurnOdd
---

# Patch

#### Fixed

- Idle watchers and grove refreshes write fewer filesystem changes. Unchanged cursors and lock files stay untouched, and watcher heartbeats update once every ten seconds.
