# Patch

#### Fixed

- **`lemonaid restore tmux` no longer loses the lemons it resumes.** Each restored row still named its pane on the server that died, so the next inbox to start archived every restored lemon as `pane-gone` until you sent it a message. Restore now records each lemon's new pane.
