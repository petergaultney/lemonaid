# Minor

#### Added

- **`lemonaid audit` shows who archived, revived, edited, restarted or tossed what, and why.** Brief archives and revives (by hand, idle sweep, place toss), edits to another lemon's brief, parent links, restarts, and inbox archives, unarchives and purges are recorded in `~/.local/state/lemonaid/logs/actions.log`, beside the place log. Each event names its actor (a Brief-ID, a channel, your login, or a lemonaid job such as `idle sweep`) and the evidence used, `via`; place log entries now carry `via` too.
