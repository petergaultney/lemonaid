# Patch

#### Fixed

- **The inbox no longer stalls behind other processes' database writes.** Each refresh took the database write lock twice, as did every push scout poll, even with nothing to write, so a busy writer could hold the inbox's keys and mouse for seconds at a time.

- **An idle inbox does less work on each refresh.** It no longer re-reads every brief to check `Hidden:`, recomputes group colors or re-resolves every row's directory three times a second.

- **The inbox's periodic refresh reads on a worker thread.** The database, briefs, `ps` and tmux are read off the event loop, so a slow read delays the next redraw rather than keys and the mouse. The inbox's own database calls wait at most 5 s for another process's lock.

#### Added

- **The inbox logs what it is stuck on while it is stuck.** A blocked event loop is logged with its full stack once it passes a second, and a key or mouse queue that stops answering, or painting held off, is logged with every busy task's await chain. A loop busy for most of a 5 s window is logged with where the time went, even when no single block is long.
