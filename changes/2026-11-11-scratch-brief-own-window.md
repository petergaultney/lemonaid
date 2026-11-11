# Patch

#### Fixed

- **The scratch pane's brief is always its own window's lemon's, after a restart, a toggle or a switch.** Pressing `b` on another window's lemon, or moving the pane through a window with no lemon, could record that brief as this window's, and the pane then kept showing it. `b` on another window's lemon now switches the main pane to it, and the pane checks in the background, each time it shows a brief, that it is its window's lemon's.
