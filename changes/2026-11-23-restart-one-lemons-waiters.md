# Minor

#### Added

- **`lemonaid watch restart <Lemon-ID>` restarts every waiter that lemon has, the ones it started by hand included, without the lemon doing anything.** Once the lemon's watcher runs (a push scout is started if it had none), each hand-started waiter (`watch pr`, `watch slack` and the rest) that the watcher follows from the brief is stopped and tells its lemon not to rearm it, and any other keeps running.

#### Fixed

- **A `lemonaid watch slack` run in the foreground registers as its lemon's waiter,** so `lemonaid watch stop --self slack` and `watch restart` can stop it. Before, only a `kill` reached it.
