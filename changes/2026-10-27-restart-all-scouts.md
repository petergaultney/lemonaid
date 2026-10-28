# Patch

`lemonaid watch restart` now restarts every watcher it selects. A waiter with a batch still waiting for delivery restarts at once and detects it again, and one that has not restarted after `--wait` seconds (default 30), or that predates the restart signal, is stopped and its push scout started again.
