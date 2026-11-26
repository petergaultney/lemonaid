# Patch

#### Fixed

- **`tell` no longer types a wake prompt into a lemon whose push scout is only restarting.** A lemon with a registered scout counts as listening while the scout host runs or restarts, instead of deaf for the seconds a restart releases its lock. The wake prompt now names `## Watching` and skips rearming when the push scout runs.
