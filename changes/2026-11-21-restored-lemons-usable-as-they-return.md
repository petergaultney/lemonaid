# Minor

`lemonaid restore` makes each lemon ready the moment it runs again: its subscriptions, its notes and any rearm prompt come right away, not after the last lemon has started. Up to `[restore] parallel` lemons start at once and the next starts as soon as one is running, so a slow lemon no longer holds up the batch behind it.

Lemons start most recently heard from first. Restore first makes every window it will fill, in the order tmux first made their sessions, so the layout and session order come back as before; until its lemon starts, a window says which lemon is coming and runs no shell.

Selecting a lemon still lost in the inbox, the grove or with `lemonaid go` while a restore runs has the restore start it next, instead of offering to resume it beside the restore. The inbox row for the restore counts the lemons back as they come.
