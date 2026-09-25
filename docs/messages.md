# Lemon messages

Each lemon with an attached brief has a stable `Lemon-ID` stored in the brief.
New IDs combine a brief slug with a short WordyBin suffix, such as
`mc-tars-no-mops-leases.SkullHen`. The ID is set once and keeps the same value
if the brief is renamed. Its file inbox is
`~/.brief-lemons/inbox/<lemon-id>/`. The ID and
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

```bash
lemonaid tell codex:thread-id "Please review the PR."
lemonaid tell <lemon-id> "Please review the PR."
lemonaid tell 2026-09-25-review "The PR is ready."
lemonaid inbox next --self --channel codex:thread-id
lemonaid inbox watch --self --channel codex:thread-id
lemonaid inbox watch --self --timeout 3600
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
`lemonaid inbox watch --self` running. The watch holds
`<inbox>/.waiter.lock` while it waits, and a second watch for the same lemon
exits with an error naming the first one's pid. The optional Stop hook
`lemonaid claude waiter-check` blocks a lemon with an attached brief (unless it
is `done`) from ending its turn while no watch holds that lock. It waits up to
three seconds for a watch that is still starting, and lets the second
consecutive stop through, so a lemon that cannot arm one is never stuck.
Install it with `lemonaid claude hooks --waiter-check` (`--uninstall` removes it).

`inbox watch --self` inside Codex still works: when `CODEX_THREAD_ID` is the
watched channel's thread (or `--codex-thread <thread>` names one), it queues the
message the same way instead of printing it. Receivers of one inbox take turns,
so the service and a watch never hand out the same message twice. A process
killed after Codex accepts a message but before the move delivers it again.

Receiving claims the file by moving it to `done/`. A failure while reading or
printing restores it to the pending folder. A process killed between the move
and printing can still leave an unread message in `done/`; check that folder
if delivery is interrupted.

`--parent` and `--child <name>` are reserved for parent links. Until those links
are stored by stable ID, they report an error; address the ID, channel, or
brief directly.

`LEMONAID_MESSAGES_DIR` overrides the inbox root. When `LEMONAID_BRIEFS_DIR`
is set, the default inbox root follows it, at `<briefs-dir>/inbox/`.
