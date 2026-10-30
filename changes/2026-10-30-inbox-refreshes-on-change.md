# Minor

#### Changed

- **The inbox reloads its list only when something it shows changed.** Each refresh now checks the database's commit counter and kqueue events on the briefs and the lemons' inboxes, and reloads otherwise every 5 seconds for ages and liveness. In a sandbox copy of a 110-lemon inbox it went from 14.6% of a core, counting the processes it starts, to 5.6%.
- **The inbox reads pane focus from the scout host.** With `lemonaid tmux labels` set up, the host's control-mode client keeps a listing of tmux's clients and panes. The inbox uses it for the focused lemon, the scratch pane's keyboard indicator and size autosave, and pane locations, instead of starting about three `tmux` processes a second.
- The stuck-PR line reads the scout host's PR snapshots before asking GitHub, and finding the Codex processes among every terminal's processes reads only each command line's first words.
