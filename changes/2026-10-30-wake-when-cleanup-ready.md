# Minor

#### Added

- **A parent hears again when a done child's place can be cleaned up.** When a child goes `done` while its cleanup is held (an unfinished grandchild, or a client attached to its tmux session), the children waiter reports it once more when the hold clears, as `<child>: cleanup ready, nothing holds its place now (held by: ...)`. Its event-note kind is `child.cleanup_ready`.
