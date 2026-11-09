# Patch

#### Changed

- **A watcher run with no brief, `--me` or harness session keeps no state.** Its cursors and lock live in a temporary directory removed when it exits, instead of a shared `anonymous` directory, so each such run starts from the current state and two of them no longer block each other.
