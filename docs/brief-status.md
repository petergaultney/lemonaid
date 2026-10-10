# Brief status: what a lemon sets and what lemonaid derives

A brief's `Status:` line is for states that need the lemon's judgment. Whether the
lemon is busy or idle is something lemonaid can see for itself, so it no longer
asks lemons to write it down.

## What a brief may say

`Status:` holds one of these words, or is left out:

| Status | Whose move |
|---|---|
| `blocked` | the user can act now |
| `alert` | the user's move is needed and harm grows while it waits |
| `review` | a teammate's approving review |
| `merge` | only the user's merge remains |
| `approve` | the user's approval of a teammate's PR |
| `running` | nobody's; the lemon is minding a long process |
| `done` | nobody's; the work is finished |

With none of these, the lemon's own state is shown. `lemonaid brief new` and child
briefs start without a `Status:` line.

## What lemonaid derives

A brief without a manual status is shown as one of:

| Shown | When |
|---|---|
| `active` | the lemon is mid-turn |
| `idle` | the lemon is between turns and will read a message sent to it |
| `deaf` | a Claude lemon is between turns with no inbox waiter armed |
| `dead` | no harness is running on the terminal the lemon last reported from |

These come from the facts `lemonaid tell` already uses to say whether a message will
be read (`docs/messages.md`). A Codex lemon always listens while its harness runs.
A Claude lemon listens while its inbox waiter holds the lock, and its Stop hook
refuses to end a turn without one. So a held lock means the lemon is reachable,
not that it waits on anything in particular: what it waits on is the `### Waiting
on` part of `## Now`, which an `idle` card shows. Harnesses lemonaid can't probe
(OpenCode, OpenClaw) show `active` or `idle` only.

A Claude lemon is briefly deaf each time its inbox waiter hands it a message,
until it rearms one, so the inbox marks `deaf` only after 15 seconds of it.

`dead` and `deaf` are also marked on a card with a manual status other than `done`,
since a `blocked` lemon that has exited will not see the answer.

## Older briefs

`Status: working` and `Status: waiting` are read as no status. `brief check` accepts
them, so an older brief does not stop a Claude lemon's turn from ending.

`lemonaid brief status --self clear` removes the `Status:` line. `working` and
`waiting` do the same, and say so, so instructions written before this change still
work.

## Where the inbox puts it

A brief with no manual status sits with the ordinary unread and read rows, as
`working` and `waiting` did. For `fold_statuses` it counts as what it shows, so
folding `idle` keeps an `active` lemon in the list, as `working` once did, and a
lemon that stops listening comes out as `deaf` or `dead`. In `fold_statuses`,
`waiting` means `idle` and `working` means `active`.

## Watching children

`lemonaid watch briefs --to` takes only manual statuses. A child that clears its
status is recorded as having none, so returning later to the same status counts as
a new entry.
