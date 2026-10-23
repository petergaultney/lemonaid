# Patch

#### Fixed

- **A watcher that stops polling is now reported deaf and replaced, instead of counted as running.** Each `watch --self` waiter records a heartbeat on every pass; after two minutes without one, `--status` says `watcher deaf`, `tell` and the inbox treat its lemon as deaf, and the Stop check, SessionStart, `tell`, the inbox and `watch --self --push` stop it and start a new scout.
