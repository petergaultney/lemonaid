# Tasks: theory and constraints

How to use tasks is in `docs/tasks.md`. This note is for changing the code: what the design commits to, and what it must not start doing.

## What a task is

- A brief specifies work; a task records whose move it is. A task has one holder at a time, and the holder is whoever moves next. Handing a task on is the turn passing.
- Tasks are a general concept. Lemonaid knows no roles such as author or reviewer; a user's own instructions may describe them, but the code never does.
- A brief's Status is the source of truth for a lemon's own state. Nothing infers a status from a brief's prose: Needs and Waiting on only say which of several tasks a status is about.
- A task always has a holder that can move. A brief that hands a task on observes it until it says otherwise, and archiving a brief hands its open tasks on first.
- Finishing work takes a second party. A lemon with a parent hands its tasks up when it goes done, into the `check` state (one held by a person stays with them, and the parent answers for it), and the holder of a checked task closes it. A lemon with no parent closes its own; a human can always close or reopen one.

## How state is kept

- The ledger is append-only. A `tasks` row is the fold of its `task_events` (`model/events.py`), so it can always be rebuilt from the log, and `ledger.consistent` says whether it was.
- Every write is conditional on the revision it read and idempotent by request ID, so a retried command returns its first result instead of acting twice.
- Messages a write causes go out only when that call committed it.

## The inspector

- The checker judges; lemonaid observes and delivers. All challenge logic and every word a lemon reads come from the checker, any program speaking the line protocol (`checker/protocol.py`). Lemonaid gathers the facts the checker declares it watches, finds working briefs that have no task, keeps the cases, and sends the messages.
- An unknown fact never supports an accusation. What lemonaid can't see is recorded as `unknown` or `unavailable`, never guessed.
- Messaging is the inspector's channel to a lemon, and it only writes to it: the inspector sends messages to inboxes but never reads an inbox. Timing comes from a task's own events (assignment, start, close) and from what lemonaid observes about a lemon, never from whether a message was read.
- A lemon taking a turn is not inspected; it may be changing its status or handing its task on.
- An open challenge is sent again with doubling gaps, and stops when a change resolves its case.
- Nothing here talks to a terminal multiplexer. Whether a lemon is running comes from lemonaid's lemon facts.

## Layering

- `model` is the ledger and imports none of the other subpackages.
- `checker` speaks only the line protocol and imports nothing from `model`, so a checker can run outside lemonaid.
- `briefs` connects briefs to tasks and builds on `model`.
- `inspection` runs passes and uses all three.
- The top-level `*_cli.py` modules are the `lemonaid task` commands.
