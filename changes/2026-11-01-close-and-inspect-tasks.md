# Minor

#### Added

- **The task inspector checks open tasks with a checker and challenges the briefs that owe a move**, again with doubling gaps while a case stays open. With `[tasks] inspect_interval` set, the scout host runs it against one long-running checker process, asking only about what changed; `lemonaid task inspect` runs a pass now. See `docs/tasks.md`.
- **A lemon that hands a task on keeps observing it, and an open task is never orphaned.** `lemonaid task observe` and `unobserve` follow a task or stop; `--instead-of OWN_TASK_ID` closes a duplicate. Archiving a brief hands its open tasks to its parent first.
- **`lemonaid task depend TASK_ID --on OTHER_TASK_ID` makes a task wait for another lemon's,** so its holder isn't challenged as idle while that one moves.
- **Tasks can be closed, reopened and given a result.** Closing one tells the holders of tasks that waited for it.
- **A task whose holder dies is reported to whoever assigned it**, or else to the nearest live lemon above them, to resume the holder or hand the task on.
- **Waiting on a lemon is a task; waiting on a person or a process is a Status.** A brief's Status now covers every task it holds, and the idle challenge asks who moves next.
- **A task is only ever held by a live lemon.** `task assign` refuses a person, an outside party, or a lemon that isn't running; a lemon waiting on a person keeps its task and sets its Status.
- **A lemon closes a task when its work is finished**, with a reason saying where the result is. The inspector checks each closing, and challenges one whose PR hasn't merged.
- **A review brief takes the work's existing task** (`--task`), and its reviewer hands the task back to the author when done. `--new-task` is refused when an open task already covers the PR; a review of a teammate's PR holds its own task, with Status `review` or `approve`.
- **The inspector challenges a Status that its task's PR contradicts:** `done` while the PR is open, or `merge` while the PR is a draft, failing CI, or already merged. A task handed to a parent by `done` while its PR is open is put to the parent to hand back.
- **`brief status done` hands a lemon's still-open tasks to its parent, in a new `check` state.** The parent closes each one or hands it back.

#### Fixed

- **`lemon doctor` shows when a Codex lemon was last active.** It used to read only Claude's transcript, so every Codex lemon showed unknown.
