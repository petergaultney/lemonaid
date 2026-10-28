---
type: Notes
created: { at: 2026-10-28T08:46:52-04:00, by: ShiftKey }
responsible-parties:
  - Peter Gaultney
contributors:
  - ShiftKey
---

# Minor

#### Added

- **Hand off by Lemon-ID or from the inbox.** `brief handoff --source` accepts a full stable ID or unique short name. `Alt+h` offers destination and mode selection with explicit confirmation.
- **Manually recover without a final outgoing turn.** Selecting Recovery in the inbox or passing `--recover --yes` uses its validated saved brief to replace the verified outgoing process in the same tmux pane. Identity and manual inbox state transfer after destination acceptance; no second live lemon or extra window is kept.
