# Minor

#### Added

- **Restart a live lemon in its own tmux pane.** `lemonaid lemon restart` resumes the same Claude or dedicated Codex session, with a dry-run plan and saved operation status, while preserving its brief and inbox identity.

#### Fixed

- Claude `/clear` rechecks its source before transferring the brief and manual state, and leaves a restarting source alone.

- Login shells such as macOS `-fish` remain eligible for same-pane restart; partial-restart refusals include the saved operation’s inspection command.
