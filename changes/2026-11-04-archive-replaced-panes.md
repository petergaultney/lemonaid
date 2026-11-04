# Patch

#### Fixed

- **The stale-session sweep archives an inbox row whose tmux pane was replaced.** It used to keep both rows when the new pane got the same tty, leaving a lemon in the inbox that could not be switched to.
