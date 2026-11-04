# Minor

#### Changed

- **A lemon's message store is its mailbox, so "inbox" means only `lma`'s attention list.** `lemonaid mailbox next|watch|deliver` replace `lemonaid inbox next|watch|deliver`, which still work, as does `watch stop --self inbox`; the waiter kind, the watch batch's source tag and `lemon doctor`'s `mailbox_waiter` fact (still also printed as `inbox_waiter`) use the new name.
- **`~/.lemons/inbox/` moves to `~/.lemons/mailbox/` on the first message command,** with a link left at the old path so an older lemonaid that is still running keeps reading the same files. Archived briefs keep their messages under the attic month's `mailbox/`, and revive still finds ones archived under `inbox/`.
