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

A task's holder is always a lemon, `brief:<Lemon-ID>`: a task records which lemon moves next, and a brief's Status records when a person's input is needed. A lemon waiting on a person keeps its task and sets its Status (`blocked` for the user, `review` for a teammate). `lemonaid task show TASK_ID` names the holder, so you can message it yourself. The previous holder is kept as the fallback contact. Assigning a task makes the receiver its holder immediately:

```bash
lemonaid task assign TASK_ID --to BRIEF --reason TEXT
```

The receiver must be live: a lemon attached to its brief whose harness runs. A dead, archived or unstarted lemon is refused, with the command to resume it. The holder hands a task on this way once it is no longer the one to move next. Anyone else who runs it takes the task, and lemonaid messages the former holder. The new holder, other than the caller, is messaged too. `task create`, `brief new` and `brief task ensure` do the same for a running brief that isn't the caller. A repeated `--request-id` sends no message again.

A brief that hands a task on, by `task assign`, by going done, or by having it taken, observes it from then on; `lemonaid task unobserve TASK_ID` stops that. To follow a task another brief holds, run `lemonaid task observe TASK_ID`. When your own task duplicates it, `--instead-of OWN_TASK_ID` also closes yours as a duplicate, in the same transaction.

An open task always has a holder that can move. Archiving a brief (by hand, by the idle sweep, or when its place is tossed) first hands each open task it holds to the nearest live lemon from its parent up, or else to the task's previous holder or sponsor while live, and refuses when no live lemon is left. When a holder that has started with its task is no longer live, the inspector tells whoever assigned the task, or failing that the nearest live lemon above them, and then above the holder, up to the root, to resume the holder or hand the task to a live lemon.

When a brief's lemon first starts, the session's launch context lists its open tasks and records the start; until then, the default checker gives the task's creator a launch grace before challenging it. Resuming the session does neither again. There is no separate acceptance step: a holder that idles with a task is challenged by the idle rule.

## Results, closing and done

```bash
lemonaid task result TASK_ID --evidence REF   # a commit, PR, document or brief; the task stays open
lemonaid task close TASK_ID --reason TEXT
lemonaid task reopen TASK_ID --reason TEXT    # back to its last holder
```

Closing a task releases every task that waited for it, and lemonaid messages each waiting task's holder to pick up the result. A lemon with a parent can't close a task it holds while working on it; going done hands the task to the parent instead, in the `check` state, and the holder of a task in `check` may close it. Anyone else may close or reopen a task, and if it isn't the caller's, its holder is told. A lemon with no parent, such as the control center, closes its own tasks.

With tasks enabled, `brief status done` hands each open task the brief holds to its parent, or the nearest live lemon above it when the parent isn't live, and puts it in the `check` state, with the reason "says this is done; check the work". A task's lifecycle is `open`, `check` or `closed`; a task in `check` is still inspected, so a parent that sits on it is challenged, and handing it on returns it to `open`. The parent gets a message saying how to close the task or hand it back. `done` is refused while the brief holds an open task and has no parent, or no live lemon above it; the refusal lists each task with the commands to close it or hand it on.

## Commands

```bash
lemonaid task list --holder self --json          # tasks you hold
lemonaid task list --tree self --json            # tasks your lemon tree holds or specifies
lemonaid task show TASK_ID --json                # state, linked briefs, dependencies, events
lemonaid task create --brief BRIEF --assign BRIEF --description TEXT [--url URL]
lemonaid task assign TASK_ID --to BRIEF --reason TEXT
lemonaid task observe TASK_ID [--instead-of OWN_TASK_ID]
lemonaid task unobserve TASK_ID
lemonaid task result|close|reopen TASK_ID ...
lemonaid task inspect [--dry-run]                  # run one inspector pass now
lemonaid task set-url TASK_ID URL --reason TEXT  # a successor PR keeps the task's ID
lemonaid task export                             # every task with its events, as JSON
lemonaid brief task ensure BRIEF
```

`--tree` follows parent links (see [lineage](lineage.md)), not task dependencies. Each task appears once, with every tree brief it connects to as `holder` or `spec`. Closed tasks need `--include-closed`.

Every change is conditional on the task's revision. A command reads the current revision once; `--expect-revision N` pins it instead. A conflict reports the current holder and revision and changes nothing. `--request-id` makes a command safe to repeat: a request that already committed returns its first result, and reusing an ID for a different change is refused.

## Replaying a checker offline

A checker is an external program that decides whether a task's holder is progressing, waiting legitimately, or needs a challenge. `lemonaid task replay CORPUS.json` runs one over saved snapshots, without a database, and lists every verdict that differs from the snapshot's `expected` value or from `--baseline`; it exits 1 if any do. Without `--checker`, it runs the default checker in `lemonaid.tasks.checker.default`.

The checker reads and writes a tab-separated line protocol, version 1. Each file starts with `protocol<TAB>1`, and `%`, tab, CR and LF in fields are written `%25`, `%09`, `%0D` and `%0A`. In the default checker, an idle holder isn't challenged while its brief's Status puts the next move on someone else: `blocked`, `alert`, `review`, `merge`, `approve` or `running`. Needs or Waiting on text never stands in for a status. A status covers a task only if it is the brief's sole open task, or Needs or Waiting on names the task's ID; if the brief holds several tasks and names none of them, the finding is unknown. A dependency counts as a wait only while the child task's own latest finding is `ok` or `wait`; a closed dependency is the holder's move once the idle grace has passed since it closed. CI known to be running on the task's PR is a wait; in any other state, or with no PR on the task, an idle holder is challenged under the idle rule, and the challenge backs off. An idle holder's grace starts no earlier than its assignment, or its lemon's start with the task, and a lemon taking a turn isn't inspected at all. An evaluate input has `context`, `case` and `fact` records and one subject: a `task`, or a `brief` (`brief<TAB>LEMON_ID<TAB>parent<TAB>PARENT_ID`, where the parent is its nearest ancestor that has a task disposition) for a working brief that has no task; a fact's availability is `known`, `unknown` or `unavailable`, and an unknown fact never supports a verdict. The output is the complete finding set for that one subject, naming it by its task ID or Lemon-ID: `ok`, `wait`, `unknown`, `challenge`, `adjudicate` and `recheck` records. Output naming another task, or mixing `ok` with a challenge, is reported as a checker failure.

## The inspector

With `[tasks] inspect_interval` above 0, the scout host runs a pass every that many seconds while it runs, which is while any lemon does. `lemonaid task inspect` runs one pass now. Only one pass runs at a time; a second one started meanwhile is skipped. Each pass evaluates every open task with the configured checker (`[tasks] checker`, or the default checker). It first asks the checker to `describe` what it watches: `task`, `lemon`, `lineage`, `pr`, `brief` or `file` keys. A `lineage` key gives a lemon and its ancestors, nearest first, and whether each is live. Then it hands `evaluate` facts for exactly those watches, the task's open cases, and what only lemonaid knows: when a task it waited for was closed, who made the current assignment, and any dependency cycle through it. A file is captured by content under the state directory's `task-captures/`, and its fact names that copy. A watch of any other kind is reported as a checker failure.

The scout host keeps one checker process running, started as `CHECKER serve`, and `task inspect` starts one for its pass. Each request is `request<TAB>ID<TAB>OPERATION` (`describe` or `evaluate`), the input as a file would hold it, and `end<TAB>ID`; the checker answers with `response<TAB>ID`, its output and `end<TAB>ID`, or one `failed<TAB>ID<TAB>REASON` line, in any order. A checker that exits or misses `checker_timeout` is started again, and its unanswered requests count as checker failures. The scout host remembers each subject's input, leaving out the pass's time and when each fact was observed, and asks the checker again only when that input changes or the earliest `recheck` or `wait` time in its findings comes, so a pass in which nothing changed asks nothing. PR facts come only from the scout host's snapshots of PRs a lemon watches: a PR becomes evidence once a lemon names it in its brief, and the inspector makes no GitHub calls of its own.

A complete finding set replaces the task's open cases. A challenge it repeats stays open and isn't sent again, and one it leaves out is resolved. A checker failure, a timeout or an `unknown` finding leaves every case as it was. A case is about one assignment and subject URL, so closing, reassigning or re-pointing the task resolves it regardless. A finding for a revision the task has moved past, or from a pass older than the task's latest evaluation, is dropped.

The same pass checks coverage. A working brief (not done, archived or dead) that has been idle longer than `policy.coverage_grace` (600 seconds), with no task, exemption or observed task, gets a missing-task case.

The inspector messages each challenge to the brief it names, so every lemon with a task is covered without configuration. A challenge still open is sent again after `[tasks] challenge_interval` seconds, then twice that, four times... up to `max_challenge_interval` (a day by default); a case that resolves and opens again with the same evidence against the same assignment, for the same recipient, as when its holder takes an unrelated turn, keeps its place in that backoff. A brief listed in `[tasks.opt_out]`, with its reason, gets none. `--dry-run`, or `challenge_interval = 0`, lists what a pass would send instead of sending it; the cases are still recorded. Lemonaid finds each working brief with no task, exemption or observed task, and hands it to the checker as a `brief` subject, the same way as a task; a brief that has one is covered without asking. The default checker challenges such a brief once it has idled past `policy.coverage_grace` (600 seconds), telling it to ask its parent to define a task, and the parent to ask the human if it isn't sure; a brief with no parent is told to run `brief task ensure`. A message is the checker's reason under a one-line header, so a custom checker writes every word a lemon reads. Adjudications, and challenges for anyone other than a brief, are listed, not sent. Each case is checked again just before it is sent, so one made stale since its evaluation sends nothing. What a lemon reads with its own tools is a fact; when lemonaid can't see something, the fact is `unknown` and the checker makes no accusation on it. Whether a lemon is still running is unknown when lemonaid has no recorded terminal for it. The inspector sends messages but never reads a lemon's inbox.

