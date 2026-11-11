# Minor

#### Added

- **A lemon whose harness crashed while tmux runs is kept, and `lemonaid restore` brings it back in its own pane.** Claude and Codex now report a quit through a `SessionEnd` hook (`lemonaid hooks install`; re-trust it in Codex's `/hooks`), and a harness that stops without one is marked `crashed` instead of archived.

#### Changed

- **`lemonaid restore` leaves out lemons recorded on another tmux server.** It used to reopen them on the server it restores into; now they are reported `not restored`, naming their socket.
- **Claude's `SessionEnd` reason `other` no longer counts as a quit.** Claude gives it for a signal, such as a shutdown's SIGTERM, so a lemon ended that way with its tmux server is restored.
