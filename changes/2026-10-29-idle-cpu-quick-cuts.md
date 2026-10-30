---
type: Notes
created: { at: 2026-10-29T21:20:00-04:00, by: RavenArt }
responsible-parties:
  - Peter Gaultney
contributors:
  - RavenArt
---
# Patch

#### Fixed

- **The Codex delivery service no longer holds a core while it runs.** Each pass rescanned every brief ever attached once per Codex lemon. It now scans once per pass and skips lemons with no pending messages.
- **Push scouts use about a third less CPU when idle.** Checking whether a lemon's children are alive read every brief attachment, even for a lemon with no children; it now reads only the children's.
- **The grove popup does no work while hidden.** It used to reload every 3 s whether or not it was showing; it now reloads when it is shown.
- **tmux status-line commands start in about half the time.** `lemonaid-tmux-window-status` and `lemonaid-tmux-session-name` no longer load lemonaid's whole tmux package, which tmux was paying for once per window per `status-interval`.
