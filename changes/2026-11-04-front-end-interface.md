# Patch

Showing, resuming and prompting a lemon, checking that its pane is still there, and `lemon start` with no target now go through one front-end interface (`lemonaid.front_end.interface`), with a module each for tmux, WezTerm and cmux. Behavior is unchanged.
