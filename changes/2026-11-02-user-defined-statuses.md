# Minor

#### Added

- **Brief statuses are configurable.** `[[brief.statuses]]` entries add Status words or change the defaults, each with its colors, glyph, rank, description, and whether it is the user's move or keeps a row in attention mode; `done` stays built in. `lemonaid brief statuses` lists them, and the inbox, the grove, watchers and the task inspector all read the same list.

#### Changed

- **`review` now covers any review or reply from outside the grove,** such as a maintainer's response, and every status but `done` counts as a wait for the task inspector. `tui.attention_statuses` is replaced by `attention = true` on a status; a config that still sets it gets a warning.
