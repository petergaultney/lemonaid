# Minor

#### Added

- **`lemonaid inbox archive` removes one card from the inbox.** `inbox unarchive` restores it.

#### Fixed

- **A session with no brief can be added to a group**, in the inbox and with `lemonaid group add NAME <channel>`. It is grouped by its channel.
- **A `claude -p` run no longer registers a card in the inbox.** Hooks from a one-shot print-mode session are dropped.
