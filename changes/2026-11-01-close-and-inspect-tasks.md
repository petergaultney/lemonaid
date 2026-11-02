# Minor

#### Added

- **The task inspector checks open tasks with a checker and challenges the briefs that owe a move**, again with doubling gaps while a case stays open. With `[tasks] inspect_interval` set, the scout host runs it against one long-running checker process, asking only about what changed; `lemonaid task inspect` runs a pass now. See `docs/tasks.md`.
- **A lemon that hands a task on keeps observing it, and an open task is never orphaned.** `lemonaid task observe` and `unobserve` follow a task or stop; `--instead-of OWN_TASK_ID` closes a duplicate. Archiving a brief hands its open tasks to its parent first.
- **Tasks can be closed, reopened and given a result.** Closing one tells the holders of tasks that waited for it.
- **A task whose holder dies is reported to whoever assigned it**, or else to the nearest live lemon above them, to resume the holder or hand the task on.
- **A task is only ever held by a live lemon.** `task assign` refuses a person, an outside party, or a lemon that isn't running; a lemon waiting on a person keeps its task and sets its Status.
- **`brief status done` hands a lemon's open tasks to its parent, in a new `check` state.** The parent closes each one or hands it back; a lemon with a parent can't close a task it is working on itself.

#### Fixed

- **`lemon doctor` shows when a Codex lemon was last active.** It used to read only Claude's transcript, so every Codex lemon showed unknown.
