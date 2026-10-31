# Minor

#### Added

- **Task objects record who holds each piece of unfinished work.** With `[tasks] enabled = true`, `brief new` gives the new brief a task, takes an existing one with `--task TASK_ID` (anyone may take a task, and its former holder is told), or records a standing exemption with `--no-task REASON`; `lemonaid task list --tree self` shows a lead every task its lemon tree holds or specifies. See `docs/tasks.md`.
- **`lemonaid task replay` runs a checker over saved snapshots offline.** It lists each verdict that differs from what the corpus expects or from a saved baseline.
