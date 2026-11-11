# Patch

#### Fixed

- **A `watch briefs --orphans` row under `## Watching` wakes a push scout for the same statuses as the command.** The scout used to wake only on `merge`, `done` and Needs asks, not `blocked`, `alert`, `approve` or `review`. It takes current child state as its baseline once after the upgrade, so check `lemonaid brief children --self` then.
- **`watch briefs --self` and `mailbox watch --self` exit 0 while a watcher for the brief runs.** They print `push scout running` or `watcher running`; `watch briefs` still records its row, and an `--orphans` row is no longer replaced by a plain one.
- **The HQ guide uses the lemon's one watcher.** It used to tell an HQ to keep `watch briefs` and `mailbox watch` running as background tasks beside it.
