# Patch

#### Fixed

- **A crashed row whose brief is `done` leaves the grove and inbox on its own.** The watcher's periodic check archives it, so rows already marked crashed no longer need `lemonaid restore dismiss`.
