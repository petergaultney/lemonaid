# Minor

Add `[tui] double_activate_focus` (off by default) and `double_activate_ms` (default 400). With the tmux scratch pane in follow mode, one click, `o` or `Enter` on a lemon row shows that lemon in the main pane and keeps keyboard focus in the inbox; a second activation of the same row inside the window, or of a lemon already shown, takes focus. Other multiplexers, which cannot show a pane without focusing it, keep the usual behavior.
