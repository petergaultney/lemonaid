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

The JSON output adds `disposition`, and `task_id` or `reason`. A taken task adds `taken_from`, and an observer link or a taken task adds `notice`, the line also printed on stderr. If the brief file was written but its task wasn't recorded, the command fails with the brief's path and the exact `lemonaid brief task ensure <brief> <options>` command that records the same disposition: the same exemption, task, or parent task. `ensure` takes the same task options. When the brief already has a disposition, it reports that one, and refuses options that contradict it. A brief attached to a running lemon has started at once (one waiting in a window starts when its lemon does), and blocks none of the caller's tasks unless `--for-task` says so. A child brief is linked to its parent at once, so the parent's tree listing shows the task before the child's lemon starts.

## Holding

A task's holder is `brief:<Lemon-ID>`, `human:<id>` or `external:<id>`; `lemonaid task show TASK_ID` names it, so you can message it yourself. The previous holder is kept as the fallback contact. Assigning a task makes the receiver its holder immediately:

```bash
lemonaid task assign TASK_ID --to BRIEF --reason TEXT
```

The holder hands a task on this way once it is no longer the one to move next. Anyone else who runs it takes the task, and lemonaid messages a former holder that is a brief (a human or external one must be told by hand). A recipient whose lemon is running, other than the caller, is messaged too; one still waiting to start gets the task in its launch context. `task create`, `brief new` and `brief task ensure` do the same for a running brief that isn't the caller. A repeated `--request-id` sends no message again.

A brief that hands a task on, by `task assign`, by going done, or by having it taken, observes it from then on; `lemonaid task unobserve TASK_ID` stops that. To follow a task another brief holds, run `lemonaid task observe TASK_ID`. When your own task duplicates it, `--instead-of OWN_TASK_ID` also closes yours as a duplicate, in the same transaction.

An open task always has a holder that can move. Archiving a brief (by hand, by the idle sweep, or when its place is tossed) first hands each open task it holds to its parent, or else to the task's previous holder or sponsor, and refuses when there is no one. A holder whose lemon is gone is challenged on behalf of the same people, the holder's parent last.

A human or external holder needs the brief that answers for it: `--to human:ID --accountable BRIEF`, and for an external party `--recheck-at TIME` (RFC 3339) as well. Lemonaid sends nothing to the human or the outside party. Messages about the task go to the accountable brief instead.

When a brief's lemon first starts, the session's launch context lists its open tasks and records the start; until then, the default checker gives the task's creator a launch grace before challenging it. Resuming the session does neither again. There is no separate acceptance step: a holder that idles with a task is challenged by the idle rule.

## Results, closing and done

```bash
lemonaid task result TASK_ID --evidence REF   # a commit, PR, document or brief; the task stays open
lemonaid task close TASK_ID --reason TEXT
lemonaid task reopen TASK_ID --reason TEXT    # back to its last holder
```

Closing a task releases every task that waited for it, and lemonaid messages each waiting task's holder to pick up the result. A lemon with a parent can't close a task it holds while working on it; going done hands the task to the parent instead, in the `check` state, and the holder of a task in `check` may close it. Anyone else may close or reopen a task, and if it isn't the caller's, its holder is told. A lemon with no parent, such as the control center, closes its own tasks.

With tasks enabled, `brief status done` hands each open task the brief holds to its parent and puts it in the `check` state, with the reason "says this is done; check the work". A task the brief answers for that a human or external party holds stays with that holder, and the parent answers for it instead, also in `check`. A task's lifecycle is `open`, `check` or `closed`; a task in `check` is still inspected, so a parent that sits on it is challenged, and handing it on returns it to `open`. A running parent gets a message saying how to close the task, ask a human, or hand it back. `done` is refused while the brief has no parent and holds an open task or answers for one; the refusal lists each task with the commands to close it or hand it on.

## Commands

```bash
lemonaid task list --holder self --json          # tasks you hold or answer for
lemonaid task list --tree self --json            # tasks your lemon tree holds, specifies or answers for
lemonaid task show TASK_ID --json                # state, linked briefs, dependencies, events
lemonaid task create --brief BRIEF --assign BRIEF --description TEXT [--url URL]
lemonaid task assign TASK_ID --to BRIEF --reason TEXT
lemonaid task observe TASK_ID [--instead-of OWN_TASK_ID]
lemonaid task unobserve TASK_ID
lemonaid task result|close|reopen TASK_ID ...
lemonaid task inspect [--loop SECONDS] [--dry-run]  # evaluate open tasks and send challenges
lemonaid task set-url TASK_ID URL --reason TEXT  # a successor PR keeps the task's ID
lemonaid task export                             # every task with its events, as JSON
lemonaid brief task ensure BRIEF
```

`--tree` follows parent links (see [lineage](lineage.md)), not task dependencies. Each task appears once, with every tree brief it connects to as `holder`, `spec` or `accountable`. Closed tasks need `--include-closed`.

Every change is conditional on the task's revision. A command reads the current revision once; `--expect-revision N` pins it instead. A conflict reports the current holder and revision and changes nothing. `--request-id` makes a command safe to repeat: a request that already committed returns its first result, and reusing an ID for a different change is refused.

## Replaying a checker offline

A checker is an external program that decides whether a task's holder is progressing, waiting legitimately, or needs a challenge. `lemonaid task replay CORPUS.json` runs one over saved snapshots, without a database, and lists every verdict that differs from the snapshot's `expected` value or from `--baseline`; it exits 1 if any do. Without `--checker`, it runs the default checker in `lemonaid.tasks.checker.default`.

The checker reads and writes a tab-separated line protocol, version 1. Each file starts with `protocol<TAB>1`, and `%`, tab, CR and LF in fields are written `%25`, `%09`, `%0D` and `%0A`. In the default checker, an idle holder isn't challenged while its brief's Status puts the next move on someone else: `blocked`, `alert`, `review`, `merge`, `approve` or `running`. Needs or Waiting on text never stands in for a status. A status covers a task only if it is the brief's sole open task, or Needs or Waiting on names the task's ID; if the brief holds several tasks and names none of them, the finding is unknown. A dependency counts as a wait only while the child task's own latest finding is `ok` or `wait`; a closed dependency is the holder's move once the idle grace has passed since it closed. CI known to be running on the task's PR is a wait; in any other state, or with no PR on the task, an idle holder is challenged under the idle rule, and the challenge backs off. An idle holder's grace starts no earlier than its assignment, or its lemon's start with the task, and a lemon taking a turn isn't inspected at all. An evaluate input has `context`, `case` and `fact` records and one subject: a `task`, or a `brief` (`brief<TAB>LEMON_ID<TAB>parent<TAB>PARENT_ID`, where the parent is its nearest ancestor that has a task disposition) for a working brief that has no task; a fact's availability is `known`, `unknown` or `unavailable`, and an unknown fact never supports a verdict. The output is the complete finding set for that one subject, naming it by its task ID or Lemon-ID: `ok`, `wait`, `unknown`, `challenge`, `adjudicate` and `recheck` records. Output naming another task, or mixing `ok` with a challenge, is reported as a checker failure.

## The inspector

`lemonaid task inspect` runs one pass, and `--loop SECONDS` repeats it until it is interrupted. Only one pass runs at a time; a second one started meanwhile is skipped. Each pass evaluates every open task with the configured checker (`[tasks] checker`, or the default checker). It first asks the checker to `describe` what it watches: `task`, `lemon`, `pr`, `brief` or `file` keys. Then it hands `evaluate` facts for exactly those watches, the task's open cases, and what only lemonaid knows: when a task it waited for was closed and the holder read that notice, and any dependency cycle through it. A file is captured by content under the state directory's `task-captures/`, and its fact names that copy. A watch of any other kind is reported as a checker failure.

A complete finding set replaces the task's open cases. A challenge it repeats stays open and isn't sent again, and one it leaves out is resolved. A checker failure, a timeout or an `unknown` finding leaves every case as it was. A case is about one assignment and subject URL, so closing, reassigning or re-pointing the task resolves it regardless. A finding for a revision the task has moved past, or from a pass older than the task's latest evaluation, is dropped.

The same pass checks coverage. A working brief (not done, archived or dead) that has been idle longer than `policy.coverage_grace` (600 seconds), with no task, exemption or observed task, gets a missing-task case.

The inspector messages each challenge to the brief it names, so every lemon with a task is covered without configuration. A challenge still open is sent again after `[tasks] challenge_interval` seconds, then twice that, four times... up to `max_challenge_interval` (a day by default); once a pass sees a change that resolves it, a later case starts over. A brief listed in `[tasks.opt_out]`, with its reason, gets none. `--dry-run`, or `challenge_interval = 0`, lists what a pass would send instead of sending it; the cases are still recorded. Lemonaid finds each working brief with no task, exemption or observed task, and hands it to the checker as a `brief` subject, the same way as a task; a brief that has one is covered without asking. The default checker challenges such a brief once it has idled past `policy.coverage_grace` (600 seconds), telling it to ask its parent to define a task, and the parent to ask the human if it isn't sure; a brief with no parent is told to run `brief task ensure`. A message is the checker's reason under a one-line header, so a custom checker writes every word a lemon reads. Adjudications, and challenges for anyone other than a brief, are listed, not sent. Each case is checked again just before it is sent, so one made stale since its evaluation sends nothing. What a lemon reads with its own tools is a fact; when lemonaid can't see something, the fact is `unknown` and the checker makes no accusation on it. Whether a lemon is still running is unknown when lemonaid has no recorded terminal for it. The inspector sends messages but never reads a lemon's inbox.

