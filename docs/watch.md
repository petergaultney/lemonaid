# Watching documents, PRs, and files

`lemonaid watch doc` blocks until someone responds to a Markdown document through
Relay Comments (inline CriticMarkup blocks written by an Obsidian plugin), and
then wakes the lemon that wrote it. It uses no model turns while it waits: it reads the file
every 15 seconds.

```bash
lemonaid watch doc --wait <doc> --me "Author (MotorHoe)" --legacy Claude --once
lemonaid watch doc --wait <doc> --me "Reviewer (SaltyEbb)" --legacy Codex --codex-thread
lemonaid watch doc --status <doc> --me "Author (MotorHoe)"
lemonaid watch openclaw start <doc> --session-key <openclaw session key> --me <name>
lemonaid watch openclaw list
lemonaid watch openclaw stop <doc>
```

## Events

- **A thread needs a reply.** A thread is an optional `{==highlight==}` followed by
  `{{author="..." ...>>text<<}}` blocks with nothing between them. It is unanswered when its
  last block is not signed `--me` or one of the `--legacy` names. The waiter reports a thread
  when it becomes unanswered, and again when an unanswered thread gains a block.
- **The body changed**, once the text outside comment threads has been unchanged for
  `--quiet` seconds (20 by default). A human can get the lemon's attention by editing the
  doc, without writing a comment. Replies inside threads don't count, and neither do the
  watching lemon's own body edits, once recorded (see below); anyone else's do, another
  lemon's included. The event gives the line delta. `--no-edits` turns this off.
- **The doc was created.** A waiter can start before its doc exists. It waits, and reports
  the doc as created once its body has been quiet for `--quiet` seconds, or, with
  `--no-edits`, reports only the threads in it.

## Ignoring the lemon's own edits

A waiter started from a Claude Code or Codex session (`CLAUDE_CODE_SESSION_ID` or
`CODEX_THREAD_ID` set) doesn't wake that session for body edits it made itself. It
adopts a changed body silently only when the session's recorded edits lead to it from the
body it last reported, so an edit someone else made earlier in the same turn still wakes it,
with a line delta that includes the lemon's own change.

- **Claude Code** records its edits through PreToolUse and PostToolUse hooks on `Edit`,
  `Write` and `MultiEdit`. Install them with `lemonaid claude hooks --own-edits`. They
  start Python only in a session that has run a doc waiter, and only for a `.md` path.
- **Codex, and a Claude edit made through Bash,** record with
  `lemonaid watch doc --editing <doc>` just before the edit and `lemonaid watch doc --mine
  <doc>` right after it. Codex has no hook to do it. `--mine` without a preceding
  `--editing` records nothing and exits 2, so the edit wakes the waiter as before.

Codex can do all three in one shell call. `apply_patch` works as a shell command inside a
compound command (checked with codex-cli 0.159.2, in the workspace-write sandbox):

```sh
lemonaid watch doc --editing <doc> && apply_patch <<'PATCH' && lemonaid watch doc --mine <doc>
*** Begin Patch
*** Update File: <doc>
...
*** End Patch
PATCH
```

The waiter replays the session's unconsumed edits in order from the body it last reported,
and stays asleep only if they chain without a gap to the body it now reads. A gap means
someone else changed the doc in between.

Records live in `<state dir>/own/<session>/`; the hook reads the default state dir, so a
waiter given another `--state-dir` sees only `--editing`/`--mine` records written with the
same flag.

Reported threads are remembered per document and `--me` name, so a waiter started later
reports only threads that are new or changed since.

## Waking the lemon

- **Claude Code:** run with `--once` as a background Bash task. It prints the first event and
  exits, and the task's completion wakes the session. Rearm after handling it, and after the
  harness stops it at its background time limit
  ([Claude setup](claude.md#2-keep-background-waiters-running)).
- **Codex:** `--codex-thread <id>` queues the first event into that thread with `codex queue`
  and exits. A bare `--codex-thread` means the lemon's own thread (`$CODEX_THREAD_ID`).
  Write it bare rather than `--codex-thread "$CODEX_THREAD_ID"`: Codex matches its allow
  rules only against commands with no shell expansions in them, so the `$` form goes to the
  approval reviewer instead ([Codex setup](codex.md#2-allow-brief-and-message-commands-under-the-automatic-approval-reviewer)). The waiter needs to write `~/.codex`, so it runs outside the workspace sandbox;
  it refuses to start if it cannot.
- **OpenClaw:** `lemonaid watch openclaw start <doc> --session-key <key> --me <name>` adds
  the doc to that session's watch list and starts one `systemd-run --user` unit per session
  if none is running. `--me` is the author name the session signs its replies with. The unit runs `lemonaid watch doc --watch-list`, which runs one agent turn in the
  session for each event (`openclaw gateway call agent`) and keeps watching. Starting a doc
  for one session removes it from every other session's list. A doc leaves the list after 7
  days with no event (`--idle-days`), and the unit exits when its list is empty.

A delivery that fails is not recorded: a one-shot waiter exits 1 and the next waiter reports
the event again; a list waiter retries on its next read.

Only one waiter may run per document and `--me` name, and one per watch list. A second exits
with status 3, naming the first. `--status` exits 0 when a waiter is running and 1 when none
is. It takes only a brief shared lock, and a waiter starting at the same moment retries rather
than refusing to start.

## State

- Locks and reported threads: `$TMPDIR/watch-doc/` (`--state-dir` moves it). `$TMPDIR` is
  used because it is writable inside Codex's sandbox.
- OpenClaw watch lists: `~/.local/state/watch-doc/lists/` (`LEMONAID_WATCH_LISTS_DIR` moves
  it).

## Watching a PR

`lemonaid watch pr` blocks until a GitHub PR changes, using one `gh api graphql` call per
`--interval` (60 seconds by default).

```bash
lemonaid watch pr --wait 90 --head <sha you handled> --comments --me "Author (MotorHoe)" --legacy Claude --once
lemonaid watch pr --wait 90 --head <sha> --comments --me "Reviewer (SaltyEbb)" --codex-thread
lemonaid watch pr --status 90 --me "Author (MotorHoe)"
```

It reports a push (the head differs from `--head`), a merge or close, a move to or from
draft, a review decision change, and with `--comments` a new comment from someone else, a
conflict with the base, or failed CI. A comment counts when it is in any
review thread, including outdated and resolved threads, a submitted review's body, or the PR conversation, and is not
from a bot or a pending review. It is skipped as your own only when it is signed: 🍋, then
your `--me` signature or a `--legacy` one, then a colon (`🍋 Author (MotorHoe): done`).
Lemons post with their human's account, so the signature is the only way to tell them apart.
Other lemons' comments wake you, signed or not, and so does an unsigned 🍋 comment of your
own from before you signed them. Comments already
reported, and the last reported draft flag and decision, are kept per PR and `--me` in
`$TMPDIR/watch-pr/`, so a rearm reports what changed in between and nothing it already
reported. Pass the head you just handled as `--head` when rearming, in full or abbreviated to
at least 7 digits; without it the first fetch is the baseline. `--repo owner/name` defaults
to the current directory's repo. It wakes Claude and Codex the same way `watch doc` does.

To skip outdated or resolved review threads, use `--skip-outdated` or `--skip-resolved`.
Set either default in [`[watch.pr]`](config.md#watchpr). The corresponding
`--no-skip-outdated` and `--no-skip-resolved` flags override those settings for one wait.
Submitted review bodies and PR conversation comments are unaffected by these filters.

`--comments` is the author's mode, so only the author is woken for merge blockers:

- A conflict is reported once per head, when GitHub says `CONFLICTING` (`UNKNOWN`, while it
  computes, is not a conflict). A waiter armed on a PR that already conflicts reports it at
  once.
- Failed CI is reported once per head, after every check on it has finished. Required
  checks count when the PR has any; otherwise every check does.
- The heads reported are kept beside the other state, so a rearm on the same head is quiet
  and a new push that still conflicts or fails is reported.

## Watching files and directories

`lemonaid watch file` blocks until a file or directory changes. It wakes Claude and Codex
the same way the other watchers do.

```bash
lemonaid watch file --wait notes.md --me "Author (MotorHoe)" --once
lemonaid watch file --wait ~/some/inbox --wait other.md --me "Author (MotorHoe)" --codex-thread
lemonaid watch file --status notes.md --me "Author (MotorHoe)"
```

- A file is reported when it is created, removed, or its contents change.
- A directory is reported when a regular file directly in it is added, removed, or
  rewritten. Hidden files and subdirectories are ignored, so a lock file or a `done/`
  folder does not wake anyone.
- A change is reported once it has been quiet for `--quiet` seconds (2 by default); paths
  are read every `--interval` seconds (5 by default).
- What was last reported is kept per set of paths and `--me` in
  `$TMPDIR/lemonaid-watch-file/`, so a rearmed waiter reports anything that changed in
  between. The first waiter for a set of paths takes their current state as its baseline.

## Watching children's briefs

`lemonaid watch briefs --children --self` waits for a direct child to enter selected brief
statuses. It follows Lemonaid's Lemon-ID parent links, including child briefs not
attached to a harness yet. Grandchildren belong to their own parent and are not watched.

```bash
lemonaid watch briefs --children --self --once
lemonaid watch briefs --children --self --to merge --to done --once
lemonaid watch briefs --children --self --codex-thread
lemonaid watch briefs --children --self --status
lemonaid watch briefs --children parent.SomeName --once
```

The first run takes existing children as its baseline. Later runs report changes since
that baseline or the last successful delivery, including children linked in the meantime.
By default, only entry into `merge` or `done` wakes the parent. Repeat `--to STATUS` to
select other destination statuses. Needs-only changes never wake, even while the child
stays in a selected status. All ignored changes advance the saved state, so the next
wake reports the latest previous status.

Values must be known brief statuses. A newly linked child wakes only if its current
status is selected. The ask reported with a status event is the first `### Needs Peter`
section (also `Needs` or `Needs you`), or an older `- Needs Peter:` bullet and its
continuation lines. Whitespace and bullet marks are normalized.

Other edits, including progress under `Next` or `Done`, do not wake the parent. Missing
or unlinked briefs are ignored; returning with the same Status and ask does not repeat
an event. A batch gives each changed child's Lemon-ID, Status, current ask, and brief path.
The parent reads those briefs, acts on them, and rearms the same command.

Reads happen every `--interval` seconds (5 by default), and a batch waits for `--quiet`
seconds without further changes to the selected events (2 by default). Ignored changes
do not postpone a pending batch. This reports the latest
observed state, rather than a history of transitions between reads. Without `--once` or
`--codex-thread`, the command keeps printing batches.

State and locks live in `$TMPDIR/lemonaid-watch-briefs/` (`--state-dir` moves them), keyed
by inbox database, parent Lemon-ID, optional `--me` watcher name, and selected target
statuses. Different target sets keep independent state; order and repeated values do
not change the key. Omitting `--to` shares state with explicit `--to merge --to done`. Different parents and named watchers keep independent state. A second waiter for the same key exits 3;
`--status` exits 0 when one is running and 1 when none is. Delivery failure leaves changes
for the next waiter. This state is separate from document, PR, and external brief watches.
