# Minor

#### Added

- **The grove window can float away from the terminal, and keeps a place for each set of displays.** Drag its top bar or an edge to leave it on another display or beside the terminal: it opens there with those displays connected and stays up after a jump, giving the terminal the focus. Left over the terminal (a tenth of its window or more, `[tui] grove_window_cover_share`), it covers the terminal and hides after a jump, as before.
- **The grove window jumps to a lemon in any terminal the inbox supports.** A lemon in WezTerm or cmux, or a tmux lemon whose pane is gone, is shown as the inbox shows it, resuming it if needed; the docs show summoning the window from WezTerm.
