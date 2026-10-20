# Minor

#### Changed

- **Lemons watching PRs share one reader.** One unified watcher per machine checks every watched PR each minute in a single small GitHub query and re-reads a PR in full only when it changed or has checks running. Other watchers read its results from files and read GitHub themselves only if it stops, so many lemons watching the same PRs use far less of the shared GitHub quota.
