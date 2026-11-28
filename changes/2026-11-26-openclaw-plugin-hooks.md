# Minor

#### Added

- **Lemonaid's OpenClaw plugin reports turns and tool calls from the gateway's own hooks.** Install it with `lemonaid openclaw plugin install` on the machine running the gateway. A lemon's own doc edits are then recorded per tool call, as Claude's and Codex's are, so someone else's edit during its turn wakes it. The plugin also marks the lemon unread and runs the rule check when a turn ends, and refuses a quiet `git push`. `lemonaid openclaw plugin status` reports a plugin left from another lemonaid version.

#### Changed

- **The scout records an OpenClaw lemon as mid-turn once the gateway accepts its turn,** where every reader sees it. It used to treat the session as busy for 5 seconds after sending.
- **An OpenClaw lemon's failed turns are kept on disk,** so its page shows them after the grove restarts.
