# Patch

#### Fixed

- **`lemonaid lemon restart` no longer refuses an exited lemon's pane because another terminal has taken its old terminal device.** Only processes left in the pane's own session count as jobs that block the restart.
