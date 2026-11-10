# Minor

#### Changed

- **`lemonaid restore` restores lemon by lemon and can be run any number of times.** A running session gains only the windows it lacks, a taken window index gives way to the next free one, and two lemons recorded in one window both come back.
- **A restored lemon counts only when its own process runs in its window.** One that fails is started once more, then left lost with the reason and listed in one `lemonaid:restore` inbox row; a lemon whose transcript is gone is not started.
- **Restored lemons keep the model and effort they were started with.** lemonaid records each harness's arguments at session start.
- **A restored lemon whose push scout reaches it gets no prompt.** Only lemons that can't be pushed to are prompted, and lemons whose processes died with the terminal are told so.

#### Added

- **`lemonaid restore` restores lost lemons in every terminal that can restore them.** Only tmux can yet; `restore tmux` stays as the same command.
- **`[restore] parallel` and `verify_seconds`** set how many lemons start at once and how long each has to prove it runs.
