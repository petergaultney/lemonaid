# Minor

#### Added

- **Restore starts by itself after tmux dies.** `[restore] auto` (`off`, `ask` or `on`; `ask` by default) decides what `lemonaid restore --auto` does when the inbox starts or finds lemons lost, or when tmux runs it at server start from a documented tmux.conf line: leave one inbox row to restore or dismiss them from, or restore them at once. A restore started by a trigger or from the inbox never starts tmux itself: lemons wait until a server runs. `lemonaid restore --into-running` does the same by hand.
- **The inbox says which running lemons a restore would miss**, in one `lemonaid:restore-readiness` row: a lemon with no recorded window or tmux server, no way to resume, or no transcript, and a running lemon pane with no inbox row.
