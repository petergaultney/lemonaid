# Minor

#### Fixed

- **`restore tmux` starts a lemon whose window is the session's first index.** With tmux's `base-index` at that index, restore failed to move the window onto itself and left the pane empty.
- **`restore tmux` gives a window to one lemon.** When several rows named the same window, the extra ones failed to start; now the most recently heard-from lemon gets it.
- **`restore tmux` ends by pointing each inbox row at the pane its lemon's process runs in.** This includes sessions it skipped, so running it again repairs rows that name the wrong pane. `--dry-run --json` now returns `{"sessions": [...], "relinked": [...]}` instead of a bare list of sessions.
- **The inbox archives sessions that were started and quit in a pane where another Claude now runs.** It used to keep every row on that tty, so each one jumped to the same lemon.
