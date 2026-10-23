# Patch

#### Changed

- **The Stop check's code moved from `lemonaid.claude` to `lemonaid.hooks`, since it serves Claude and Codex alike.** Its log lines are now named `hooks.stop_check`; `lemonaid claude waiter-check` and the installed hooks are unchanged.
