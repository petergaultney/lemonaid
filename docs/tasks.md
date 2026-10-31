# Tasks

A task records who must act next on one piece of unfinished work. It has a stable ID (`task:<uuid>`), a one-line description, one holder at a time, and an append-only event history. The brief still specifies the work; the task only says who holds it.

Task support is off until you set `[tasks] enabled = true` (see [config](config.md#tasks)).

## Creating tasks with briefs

With tasks enabled, `brief new` gives the new brief exactly one task disposition before it reports success. That covers both an unattached `--child` brief and one attached to a running lemon with `--self`, `--session`, `--channel` or `--id`:

| Options | Result |
|---|---|
| none, or `--new-task` | A new task held by the new brief, sponsored by its parent. |
| `--task TASK_ID` | The new brief becomes the existing task's holder. Use this for a reviewer once you're ready to wait on it. Anyone can take a task: if the caller didn't hold it, the former holder gets a message saying who has it now. It's refused if the task changed hands after the command checked it. |
| `--task TASK_ID --observe` | The brief is linked to the task without taking it, and the command says the holder hasn't changed. |
| `--no-task REASON` | A standing role (coordination, monitoring, on call) records why it has no task. |

A template listed in `[tasks] existing_task_templates`, `review` by default, refuses to run without `--task TASK_ID` (or `--observe`), or `--new-task` for an independent review, so a reviewer never silently gets a second task for the same work.

A new child task blocks the parent's own task when the parent holds exactly one; it then counts as the parent waiting for the child. If the parent holds several, choose one with `--for-task TASK_ID`, or say the work blocks none of them with `--independent`. A cycle of tasks waiting on each other is refused.

The JSON output adds `disposition`, and `task_id` or `reason`. A taken task adds `taken_from`, and an observer link or a taken task adds `notice`, the line also printed on stderr. If the brief file was written but its task wasn't recorded, the command fails with the brief's path and the exact `lemonaid brief task ensure <brief> <options>` command that records the same disposition: the same exemption, task, or parent task. `ensure` takes the same task options. When the brief already has a disposition, it reports that one, and refuses options that contradict it. A brief attached to a running lemon starts its acknowledgment clock at once (one waiting in a window starts it when its lemon does), and blocks none of the caller's tasks unless `--for-task` says so. A child brief is linked to its parent at once, so the parent's tree listing shows the task before the child's lemon starts.

## Holding and acknowledging

A task's holder is `brief:<Lemon-ID>`, `human:<id>` or `external:<id>`; `lemonaid task show TASK_ID` names it, so you can message it yourself. The previous holder is kept as the fallback contact. Assigning a task makes the receiver its holder immediately:

```bash
lemonaid task assign TASK_ID --to BRIEF --reason TEXT
```

The holder hands a task on this way, for example to a reviewer that was observing it. Anyone else who runs it takes the task, and lemonaid messages a former holder that is a brief (a human or external one must be told by hand). A recipient whose lemon is running is messaged too. The assignment records `delivery: message`, and the default checker makes no acknowledgment accusation until that message's delivery is known; one still waiting to start gets the task in its launch context. Assigning to a human or external holder isn't available yet. A repeated `--request-id` sends no message again. Acknowledgment is a separate, explicit step:

```bash
lemonaid task acknowledge TASK_ID
```

When a brief's lemon first starts, the session's launch context lists its open tasks and the command for each unacknowledged one. That first start also starts the acknowledgment clock; before it, only the launch grace applies. Resuming the session does neither again.

## Commands

```bash
lemonaid task list --holder self --json          # tasks you hold or answer for
lemonaid task list --tree self --json            # tasks your lemon tree holds, specifies or answers for
lemonaid task show TASK_ID --json                # state, linked briefs, dependencies, events
lemonaid task create --brief BRIEF --assign BRIEF --description TEXT [--url URL]
lemonaid task assign TASK_ID --to BRIEF --reason TEXT
lemonaid task set-url TASK_ID URL --reason TEXT  # a successor PR keeps the task's ID
lemonaid task export                             # every task with its events, as JSON
lemonaid brief task ensure BRIEF
```

`--tree` follows parent links (see [lineage](lineage.md)), not task dependencies. Each task appears once, with every tree brief it connects to as `holder`, `spec` or `accountable`. Closed tasks need `--include-closed`.

Every change is conditional on the task's revision. A command reads the current revision once; `--expect-revision N` pins it instead. A conflict reports the current holder and revision and changes nothing. `--request-id` makes a command safe to repeat: a request that already committed returns its first result, and reusing an ID for a different change is refused.

## Replaying a checker offline

A checker is an external program that decides whether a task's holder is progressing, waiting legitimately, or needs a challenge. `lemonaid task replay CORPUS.json` runs one over saved snapshots, without a database, and lists every verdict that differs from the snapshot's `expected` value or from `--baseline`; it exits 1 if any do. Without `--checker`, it runs the default checker in `lemonaid.tasks.checker.default`.

The checker reads and writes a tab-separated line protocol, version 1. Each file starts with `protocol<TAB>1`, and `%`, tab, CR and LF in fields are written `%25`, `%09`, `%0D` and `%0A`. In the default checker, a dependency counts as a wait only while the child task's own latest finding is `ok` or `wait`; a released wait (finished CI, a closed dependency) is the holder's move only once the release was delivered to it and the idle grace has passed. An evaluate input has `context`, `task`, `case` and `fact` records; a fact's availability is `known`, `unknown` or `unavailable`, and an unknown fact never supports a verdict. The output is the complete finding set for that one task: `ok`, `wait`, `unknown`, `challenge`, `adjudicate` and `recheck` records. Output naming another task, or mixing `ok` with a challenge, is reported as a checker failure.
