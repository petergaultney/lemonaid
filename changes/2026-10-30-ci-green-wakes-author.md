# Minor

#### Changed

- **A PR author hears when CI it saw running or failed passes.** The `ci-green` event wakes the author when CI passes after the watcher saw it running or failed, on a PR out of draft, with or without `--ci`, and tells it to recheck readiness and restore `merge`.
