# Patch

#### Fixed

- **A new doc comment reaches its lemon within seconds while the doc is still being edited.** Under `watch --self`, a comment used to wait until the file went unchanged for a whole read interval (15 seconds for a `watch doc` row), so a run of edits could hold it for minutes. Docs are now read every second, and the 3-second settle is timed from the file's last write when its modification time is plausible.
- **The lemonaid log records when each watch event is detected, discarded or delivered, and when a batch is queued into Codex**, so a slow wake can be traced.
