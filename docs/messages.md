# Lemon messages

Each lemon with an attached brief has a stable `Lemon-ID` stored in the brief.
New IDs combine a brief slug with a short WordyBin suffix, such as
`mc-tars-no-mops-leases.SkullHen`. The ID is set once and keeps the same value
if the brief is renamed. Its file inbox is
`~/.lemons/inbox/<lemon-id>/` (`~/.brief-lemons/inbox/` before `lemonaid home
migrate`; see `docs/home.md`). The ID and
inbox stay the same when the brief is renamed or attached to another session.
New briefs receive an ID when created; lemonaid adds one to an existing brief
when it is attached or first used for messaging. `lemonaid brief id --channel
<channel>` prints the ID. A pending message is a Markdown file in the inbox;
receiving it moves it to `done/` and prints its contents.
The one-time backfill edits the brief, including a recipient's brief when a
message is first sent to it.
Older hexadecimal and hand-made IDs remain valid and keep their inbox folders.
An ID is accepted as an opaque string when it is safe as one folder name:
non-empty, at most 255 UTF-8 bytes, with no slash, backslash, control
character, or leading dot.

## Rerolling an ID

`lemonaid brief id --self --reroll` gives a lemon a new random WordyBin, keeping the slug;
`--set QuickOdd` picks one (any two-word WordyBin, in any case). It refuses a WordyBin
another lemon has, or had. With `[brief] name` set, `--reroll` asks that command for the
new name and `--set` takes any name of letters, digits, `_` and `-`. Everything recorded against the old ID moves to the new one:

- the brief's `Lemon-ID:` line;
- the inbox folder, with its pending messages and `done/`;
- parent links, as parent and as child.

The old ID stays an alias. `tell`, `lemon parent --set`, and `place open --parent` accept it,
and its inbox folder is left holding only a `.forward` file naming the new ID. A message
written there by a sender that looked up the ID before the reroll follows the forward, so none
is left behind. The reroll holds the lock every brief and message write takes, so no write lands
halfway through it.

A running `inbox watch` for the old ID exits with `Lemon-ID changed to <new>; rearm the waiter`.
The command prints the old and new signing names (the WordyBin halves); pass the old one to
doc waiters as `--legacy`.

```bash
lemonaid tell codex:thread-id "Please review the PR."
lemonaid tell <lemon-id> "Please review the PR."
lemonaid tell 2026-09-25-review "The PR is ready."
lemonaid inbox next --self --channel codex:thread-id
lemonaid inbox watch --self --channel codex:thread-id
lemonaid inbox watch --self --timeout 3600
lemonaid watch stop --self inbox
```

`tell` accepts a lemon ID, attached channel, or unique attached brief filename
(with or without `.md`). The recipient must have an attached brief. Pass `-`
as the message to read Markdown from stdin. Sender and `--self` identity come
from `LEMONAID_CHANNEL`, a Claude session or Codex thread ID exported by the
harness, or the one live lemon recorded at the current tmux pane, in that
order. Pass `--channel` to override receive identity. A harness session ID or
an explicit `--channel` works without tmux for `tell`, `next`, and `watch`.
When an attached lemon sends, `From:` includes its stable ID, channel, and
brief name. A send from a person
without a lemon identity uses `$USER` (or `unknown`); an unattached session uses
its channel. Receiving with `--self` still requires a lemon. Sending by ID
requires that the recipient's brief is currently attached to a session.
`next` exits with status 1 if no message is waiting. `watch` waits for one message and then exits; `--timeout`
bounds that wait. The watch keeps the stable ID if the brief file is renamed,
and ends with an error if the brief moves to another channel or is detached.

## Will it be read?

`tell` writes the message, prints its path, then prints one line on stderr saying whether the recipient will read it, judged from what is running at that moment:

| State | Meaning | Exit |
|---|---|---|
| `listening` | A Codex lemon whose harness is running (the delivery service queues the message into its thread), or a Claude lemon whose inbox waiter is armed | 0 |
| `mid-turn` | A Claude lemon working on a turn; its Stop hook makes it arm a waiter when the turn ends | 0 |
| `not started` | The brief is attached to a lemon that hasn't started yet; it reads its inbox when it does | 0 |
| `unknown` | A harness other than Claude or Codex, which lemonaid can't check | 0 |
| `asking` | A Claude lemon stopped mid-turn at a question for its user, such as a permission prompt | 1 |
| `deaf` | A Claude lemon that is idle with no inbox waiter | 1 |
| `dead` | No harness runs on the terminal the lemon last reported, or its row is archived and the terminal is unknown | 1 |

A `dead` or `deaf` lemon's message stays in its inbox, so it reads it once it is resumed or rearms its waiter. Unless it finished its work, `tell` brings it back first:

- **An exited harness** (`dead`) is resumed starting on a prompt to run `lemonaid inbox next --self` and rearm its waiters: in a new window of its recorded tmux session, or in cmux, a new workspace that doesn't take focus. In any other terminal the sender gets the command that resumes it.
- **An idle Claude with no waiter** (`deaf`) in tmux has that prompt typed into its pane, but only when the pane shows an empty prompt and no dialog. The pane is the one on the lemon's recorded terminal: if a different session now runs there, it is the one prompted. lemonaid can't type into cmux, so an idle cmux lemon is only reported.
- **A Claude stopped at a question** (`asking`) is left alone, since typing would answer it; the sender is told to tell its user.
- **A lemon whose brief says `done`, or whose inbox row is archived,** is left alone. The sender gets its Status, the first line of its `## Now`, and the command that would resume it.

A second `tell` within a minute of a start doesn't start the lemon again. After 3 starts in 20 minutes (`autoresume_max`, `autoresume_window`), `tell` stops starting it, tells the sender it is crash-looping, and posts an alert to the inbox; a lemon dead again within three minutes of a start counts that start twice. A snoozed lemon is resumed too, and its row stays snoozed. Each start, and each failed start, adds a line to the inbox under `lemonaid:autoresume`. `[messages] autoresume` in [config](config.md#messages) chooses which harnesses are brought back.

Every message `tell` exits 1 for is also appended to `dead-letters.jsonl` in the inbox root (`~/.lemons/inbox/dead-letters.jsonl` by default), one JSON object per line with `at`, `from`, `to`, `state`, `said` (the line the sender saw) and `message` (the queued file). Whoever minds the lemons can wait on it with `lemonaid watch file --wait <path>`.

`tell` exits 0 when a resume or prompt was started (it doesn't wait to see the lemon come up), and 1 when it won't read the message: it finished, autoresume is off for it, or starting it failed. Its stderr line says what to do next. Sending the message again would only deliver it twice.

`lemonaid lemon resume <lemon>` starts or prompts one lemon the same way, on request: it also resumes a lemon marked `done` or archived, ignores `[messages] autoresume`, and counts against the same start limit. See [for lemons](for-lemons.md#bringing-one-back-lemon-resume).

## Delivery

A Codex lemon arms nothing. The delivery service queues each pending message
into the recipient's thread with `codex queue --thread <thread> --message
"lemonaid message: <message>"`, and moves the file to `done/` only after that
succeeds. A failed queue leaves the message pending, and the service retries
that inbox every 30 seconds. An archived Codex session is skipped; its
messages wait until the lemon is seen again.

The service starts itself: `tell` starts it when the recipient is a Codex
lemon, and a Codex turn ending with messages pending starts it too. It runs
detached (no terminal or tmux needed), and it exits once no Codex inbox has
had anything pending for two minutes. One service runs at a time, held by
`<inbox root>/.delivery.lock`, so starting it again does nothing. To run it
yourself, for example under launchd or systemd:

```bash
lemonaid inbox deliver                 # until idle for 120s
lemonaid inbox deliver --idle-exit 0   # forever
```

Its log lines go to `/tmp/lemonaid.log` (`messages.service`).

A Claude lemon can only be woken by its own background task, so it keeps
`lemonaid inbox watch --self` running, and rearms it whenever the harness
stops it. Claude Code stops background tasks after 30 minutes unless the
user raises the limit; see [Claude setup](claude.md#2-keep-background-waiters-running).
The watch holds
`<inbox>/.waiter.lock` while it waits, and a second watch for the same lemon
exits with an error naming the first one's pid. The optional Stop hook
`lemonaid claude waiter-check` blocks a lemon with an attached brief (unless it
is `done`) from ending its turn while no watch holds that lock. It waits up to
three seconds for a watch that is still starting, and lets the second
consecutive stop through, so a lemon that cannot arm one is never stuck.
Install it with `lemonaid claude hooks --waiter-check` (`--uninstall` removes it).

The optional PostToolUse hook `lemonaid claude status-note` reminds a lemon whose
brief is `blocked`, `alert`, `merge` or `approve` what its `Needs` bullets ask, so it updates
Status once an answer moves the work on. It speaks on the first tool call of a
turn (a wake from a background task is a turn too) and adds about fifty tokens
of context; it never blocks or starts a turn. The installed command is a `sh -c`
one-liner that exits without starting Python on every later tool call of the
turn, which takes about 20 ms instead of 150. Install it with
`lemonaid claude hooks --status-note`. A message the delivery service queues
into a Codex thread ends with the same reminder.

A lemon's first turn of each day starts with one line giving the time,
weekday and date ("It's 9:14am Thursday, 2026-10-01."), since a long session
keeps the date it started with. A day starts at `[inbox] day_starts` (06:00 by
default; see [config](config.md#inbox)). Claude gets it from the UserPromptSubmit
hook `lemonaid claude submit`, which fires on a background-task wake as well as
a typed prompt, and a Codex thread at the end of its first queued message of the
day. The last day told is kept per session in `<state>/date-line/`. The check is
a config load and a file read, about 0.25 ms, in a hook that already runs.

`inbox watch --self` inside Codex still works: when `CODEX_THREAD_ID` is the
watched channel's thread (or `--codex-thread <thread>` names one), it queues the
message the same way instead of printing it. Receivers of one inbox take turns,
so the service and a watch never hand out the same message twice. A process
killed after Codex accepts a message but before the move delivers it again.

Receiving claims the file by moving it to `done/`. A failure while reading or
printing restores it to the pending folder. A process killed between the move
and printing can still leave an unread message in `done/`; check that folder
if delivery is interrupted.

`lemonaid tell --parent "..."` sends to the caller's parent, and
`tell --child <lemon> "..."` to one of its children, by the links in
`lemonaid lemon parent` (see `docs/lineage.md`). A child that hasn't started
yet has an inbox already, so its messages wait there.

`LEMONAID_MESSAGES_DIR` overrides the inbox root. When `LEMONAID_BRIEFS_DIR`
is set, the default inbox root follows it, at `<briefs-dir>/inbox/`.
