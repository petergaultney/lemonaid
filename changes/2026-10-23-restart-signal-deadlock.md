# Patch

#### Fixed

- **A watcher asked to restart twice in quick succession no longer deadlocks.** Its signal handler took a lock that a second signal could re-enter, leaving the waiter alive and registered but never delivering again; `watch --self --status` still reported it running. Waiters already stuck this way ignore restart requests and need `lemonaid watch stop` and a rearm.
