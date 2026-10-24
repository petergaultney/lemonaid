# Minor

#### Added

- **`lemon start :4` starts a lemon in window 4 of your own tmux session.** It finds the session from your pane, so it works after the session is renamed; `brief attach --session :4` works the same way. `SESSION:WINDOW` still names another session.

#### Fixed

- **Jumping to a lemon in a renamed tmux session works at once.** `lemonaid go`, the grove and the inbox matched the old session name until the watcher re-recorded it; they now match on tmux's session id, which a rename keeps.
