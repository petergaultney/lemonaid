# Patch

#### Fixed

- **`lemon resume`, `tell`'s autoresume and `lemon doctor` no longer take another lemon on a reused terminal for this one.** A lemon whose old tty now runs a different Claude or Codex is reported dead and started in a new window. A wake prompt is typed only into a pane whose process is that lemon alone, and a lemon running on a terminal its row doesn't record is not started a second time.
