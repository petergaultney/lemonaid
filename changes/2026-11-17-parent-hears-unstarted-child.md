# Minor

#### Added

- **A parent hears when a lemon it started never takes up its brief.** Its watcher reports `unstarted` when no lemon claims the brief within 5 minutes of a `lemon start` or `place open --brief` made in the last hour, and `untouched` when the lemon goes idle with no Status, an empty `## Now`, and its brief unchanged since it started.
- **A lemon that can't start its brief tells its parent.** The `brief` skill and the review template now say to run `lemonaid tell --parent "<why>"` before ending the turn.
- **`lemon start` prints the directory it started the lemon in**, next to its window.
