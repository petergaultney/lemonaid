# Minor

#### Changed

- **The inbox keeps a lemon lost with its tmux server instead of archiving it, and `restore tmux` brings back only lost lemons.** A lemon is lost when no server runs on its recorded socket or a newer one replaced it; a pane closed on a running server, a harness that ended itself (including `/clear`) and a tossed place stay archived.
- **Each archived row records why it ended**, as `ended` in its metadata (`server-lost`, `pane-closed`, `user-exit`, `replaced`, `tossed`, `archived`, `dismissed`, ...).

#### Added

- **`lemonaid restore dismiss [LEMON ...|--all]`** archives lost lemons instead of restoring them, for a server killed on purpose.
