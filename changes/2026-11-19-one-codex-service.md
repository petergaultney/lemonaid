# Minor

#### Changed

- **lemonaid asks Codex about its threads instead of reading Codex's files.** The scout host keeps one private `codex app-server`, turn state and activity come from Codex's hooks, and no rollout file, session index or `lsof` listing is read; run `lemonaid hooks install --harness codex` and trust the new `lemonaid: turn` hooks in Codex's `/hooks`.
- **A Codex thread is gone only when Codex says so.** When Codex can't be asked, restore, `lemon resume` and `tell --wake` no longer refuse a lemon because its rollout file is missing.
- **A Codex lemon's context column shows tokens without a window.** Codex's hooks report the tokens sent but no context window, so the share appears only where an earlier version recorded one.
- **`lemonaid usage` reads Codex's rate limits from Codex's own account report.**

#### Removed

- **Handling of Codex's stand-in thread IDs from October 2026.** A notification whose ID differs from its thread's no longer takes over another lemon's channel, and inbox refresh no longer archives such duplicates.
