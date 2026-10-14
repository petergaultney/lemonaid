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
`CODEX_THREAD_ID` set, or `--codex-thread`) doesn't wake that session for body edits it
made itself. It adopts a changed body silently only when the session's recorded edits lead
to it from the body it last reported, so an edit someone else made earlier in the same turn
still wakes it, with a line delta that includes the lemon's own change.

- **Hooks record them, whatever the tool.** `lemonaid hooks install` adds PreToolUse and
  PostToolUse hooks to Claude Code and Codex. Before and after each tool call whose input
  names a watched doc's file (an `Edit` path, an `apply_patch`, a shell command such as
  `sed -i ... review.md` or `python3 fix.py review.md`), they hash that doc and record a
  change in between as the lemon's own. A change during any other call, such as a long
  test run, is taken as someone else's, so a script that edits the doc without naming it
  wakes the lemon once. A human edit saved during a call that names the doc is
  misattributed. The hooks start Python only in a session that has run a doc or PR
  waiter, and `lemonaid watch stop --self doc <doc>` ends that for the doc.
- **Without the hooks,** record an edit with `lemonaid watch doc --editing <doc>` just
  before it and `lemonaid watch doc --mine <doc>` right after it. `--mine` without a
  preceding `--editing` records nothing and exits 2, so the edit wakes the waiter as before.
- **Reformatting is never a change.** The body is compared with runs of whitespace
  collapsed, the spaces around table pipes removed, and table separator dashes shortened,
  so Obsidian re-padding a table wakes nobody, whoever did it.

The waiter replays the session's unconsumed edits in order from the body it last reported,
and stays asleep only if they chain without a gap to the body it now reads. A gap means
someone else changed the doc in between.

Records live in `~/.local/state/lemonaid/own-edits/<session>/`, whatever `--state-dir` a
waiter uses.

Reported threads are remembered per document in the lemon's cursors (see
[Cursors](#cursors)), so a waiter started later reports only threads that are new or
changed since. A first waiter reports every unanswered thread, since each is still waiting
on the lemon.

## Waking the lemon

- **Claude Code:** run with `--once` as a background Bash task. It prints the first event and
  exits, and the task's completion wakes the session. Rearm after handling it, and after the
  harness stops it at its background time limit
  ([Claude setup](claude.md#2-keep-background-waiters-running)).
- **Codex:** `--codex-thread <id>` queues the first event into that thread with `codex queue`
  and exits. A bare `--codex-thread` means the lemon's own thread (`$CODEX_THREAD_ID`).
  Write it bare rather than `--codex-thread "$CODEX_THREAD_ID"`: Codex matches its allow
  rules only against commands with no shell expansions in them, so the `$` form goes to the
  approval reviewer instead ([Codex setup](codex.md#3-allow-brief-and-message-commands-under-the-automatic-approval-reviewer)). The waiter needs to write `~/.codex`, so it runs outside the workspace sandbox;
  it refuses to start if it cannot.
- **OpenClaw:** `lemonaid watch openclaw start <doc> --session-key <key> --me <name>` adds
  the doc to that session's watch list and starts one `systemd-run --user` unit per session
  if none is running. `--me` is the author name the session signs its replies with. The unit runs `lemonaid watch doc --watch-list`, which runs one agent turn in the
  session for each event (`openclaw gateway call agent`) and keeps watching. Starting a doc
  for one session removes it from every other session's list. A doc leaves the list after 7
  days with no event (`--idle-days`), and the unit exits when its list is empty.

A delivery that fails is not recorded: a one-shot waiter exits 1 and the next waiter reports
the event again; a list waiter retries on its next read.

Only one waiter may run per document and lemon, and one per watch list. A second exits
with status 3, naming the first. `--status` exits 0 when a waiter is running and 1 when none
is. It takes only a brief shared lock, and a waiter starting at the same moment retries rather
than refusing to start.

## Cursors

Every watcher (`doc`, `pr`, `file` and `briefs`) compares what it watches with a saved
record of what it last reported to the lemon, its cursor, and reports what differs. So a
push, comment or edit made while no waiter ran is reported by the next waiter, and nothing
is reported twice.

- **A waiter never reports what is already true.** Read the current state yourself before
  starting a first waiter (`gh pr view`, `gh pr checks`, the doc). A missing cursor means
  the lemon has just looked, so a first waiter takes the current state as seen: the PR's head, state, comments and CI result, a doc's body, a directory's
  files, the children's statuses. Unanswered doc threads are the exception, and are
  reported, since each is still waiting on the lemon.
- **Cursors belong to the lemon, not the signature.** They live in
  `~/.local/state/lemonaid/cursors/<Lemon-ID>/` (under `LEMONAID_STATE_DIR` when set),
  keyed by the Lemon-ID of the caller's attached brief, current through rerolls. A lemon
  signing as `Author (X)` on one waiter and `Reviewer (X)` on another shares one set. A
  caller with no brief is keyed by its `--me` signature.
- **Delivery is at least once.** A cursor advances only after the event is printed or
  queued, and is replaced whole (written to a temporary file, then renamed), so a crash
  leaves the old cursor or the new one. A crash between the two reports the event again.
- **Codex can write them.** Lemonaid passes its state directory to the Codex lemons it
  starts as a writable root; a Codex started some other way needs
  `~/.local/state/lemonaid` in its `sandbox_workspace_write.writable_roots`.
- `--state-dir` puts one waiter's cursors and lock elsewhere, keyed by `--me` as before.
  Deleting a cursor loses whatever changed since its last report.

## State

- Cursors and locks: see [Cursors](#cursors).
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

It reports a push (the head differs from the one last reported, or from `--head`) that the
lemon didn't make itself, a merge or close, a move to or from
draft, a review decision change, and with `--comments` a new comment from someone else, a
conflict with the base, or failed CI. A comment counts when it is in any
review thread, including outdated and resolved threads, a submitted review's body, or the PR conversation, and is not
from a bot or a pending review. It is skipped as your own only when it is signed: 🍋, then
your `--me` signature or a `--legacy` one, then a colon (`🍋 Author (MotorHoe): done`).
Lemons post with their human's account, so the signature is the only way to tell them apart.
Other lemons' comments wake you, signed or not, and so does an unsigned 🍋 comment of your
own from before you signed them. The head and state, comments already reported, and the
last reported draft flag and decision are kept in the lemon's [cursors](#cursors), so a
rearm reports what changed in between, a push or merge included, and nothing it already
reported. `--head`, in full or abbreviated to at least 7 digits, overrides the saved head;
a first waiter without it takes the current head as seen. With lemonaid's hooks installed
(`lemonaid hooks install`), a `git push` the lemon ran itself is recorded from its output,
and a move to that head doesn't wake it (`git push -q` prints no heads, so a quiet push isn't recognized); GitHub can't say who pushed, since every lemon
pushes under its human's account. `--wait` and `--status` take a
PR number or a `github.com` pull request URL. A URL names the repo itself, so `--repo` is
unneeded, and an error if it names a different repo. For a number, `--repo owner/name` defaults
to the current directory's repo. It wakes Claude and Codex the same way `watch doc` does.

To skip outdated or resolved review threads, use `--skip-outdated` or `--skip-resolved`.
Set either default in [`[watch.pr]`](config.md#watchpr). The corresponding
`--no-skip-outdated` and `--no-skip-resolved` flags override those settings for one wait.
Submitted review bodies and PR conversation comments are unaffected by these filters.

`--comments` is the author's mode, so only the author is woken for merge blockers:

- A conflict is reported once per head, when GitHub says `CONFLICTING` (`UNKNOWN`, while it
  computes, is not a conflict). A first waiter takes a conflict that already exists as seen.
- Failed CI is reported once per head, after every check on it has finished. Required
  checks count when the PR has any; otherwise every check does.
- The heads reported are kept beside the other state, so a rearm on the same head is quiet
  and a new push that still conflicts or fails is reported.

Add `--ci` when you want a completion event whether CI passes or fails. It works
with or without `--comments`, and with `--once` or `--codex-thread`. Completion waits
for every check on the current head to finish; required checks determine the result
when any exist, otherwise every check counts. No checks is not a completion. A first
waiter takes a CI result that has already finished as seen, so check `gh pr checks` before
arming one. A pass is reported only when the same set of checks had passed on the previous poll too,
so it can arrive one `--interval` after the checks finish; if the set of checks changes
afterward on the same head (a workflow queues more jobs), the new pass is reported again.
The event names the result and head. Results are remembered per head and watcher
identity, including failures already reported by `--comments`, so rearming with
`--head` does not repeat a handled completion. A new push is reported normally; rearm
with `--ci` to wait for that head's checks. Remove `--ci` after handling the result.
A waiter armed without `--ci` while checks on the head are still pending prints a
one-line hint to stderr, and repeats it at the start of its first event.

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
- `--ignore-removed` reports only arrivals and changes. A file that is removed or moved
  away (for example into `done/` once handled) does not wake the waiter, but the saved state
  still advances past it, so a later arrival is reported normally.
- A change is reported once it has been quiet for `--quiet` seconds (2 by default); paths
  are read every `--interval` seconds (5 by default).
- What was last reported is kept per set of paths in the lemon's [cursors](#cursors), so a
  rearmed waiter reports anything that changed in between. The first waiter for a set of paths takes their current state as its baseline.

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
status is selected. The ask reported with a status event is the first `### Needs <name>`
section (also a bare `### Needs`), or an older `- Needs <name>:` bullet and its
continuation lines. Whitespace and bullet marks are normalized.

A Claude lemon with children cannot end its turn until some `watch briefs --children`
waiter is running for it. Any form counts, including `--orphans`, `--to` and `--me`, whichever
lemon started it, so one `--orphans` waiter is enough and no second one is needed. The hook
does not check which statuses the waiter wakes on.

### Also watching briefs no live lemon owns

`--orphans` adds every attached brief that has no parent link, or whose parent's session is
gone, to what `--children` watches. A brief a live lemon owns stays out, so a lead's own
children are never reported to its parent. A control-center lemon uses this to hear about
lemons that nobody else is watching.

```bash
lemonaid watch briefs --children --orphans --self --once
lemonaid watch briefs --children --orphans --self --to blocked --to done --once
```

- `--to` defaults to `blocked`, `alert`, `merge`, `approve`, `review` and `done`; passing
  `--to` replaces that set. `running` stays quiet unless selected, and a child that clears its status never wakes it.
- A Needs ask that appears or changes wakes even when the status does not, which
  `--children` alone never does.
- If tmux cannot list its sessions, a brief that has a parent link counts as owned and
  stays quiet.
- State is kept separately from a plain `--children` waiter with the same `--me`.

Other edits, including progress under `Next` or `Done`, do not wake the parent. Missing
or unlinked briefs are ignored; returning with the same Status and ask does not repeat
an event. A batch gives each changed child's Lemon-ID, Status, current ask, and brief path.
The parent reads those briefs, acts on them, and rearms the same command.

Reads happen every `--interval` seconds (5 by default), and a batch waits for `--quiet`
seconds without further changes to the selected events (2 by default). Ignored changes
do not postpone a pending batch. This reports the latest
observed state, rather than a history of transitions between reads. Without `--once` or
`--codex-thread`, the command keeps printing batches.

State and locks live in the calling lemon's [cursors](#cursors), keyed by inbox database,
parent Lemon-ID, and selected target statuses (and `--me`, with `--state-dir`). Different target sets keep independent state; order and repeated values do
not change the key. Omitting `--to` shares state with explicit `--to merge --to done`. Different parents keep independent state. A second waiter for the same key exits 3;
`--status` exits 0 when one is running and 1 when none is. Delivery failure leaves changes
for the next waiter. This state is separate from document, PR, and external brief watches.

## Recording watches in a brief

When the calling lemon has an attached brief, `watch doc`, `watch pr`, `watch file`, and `watch briefs` automatically record their restartable command in its final `## Waiters` section after startup checks pass. With `--codex-thread`, the recipient thread’s attached brief is used instead of caller detection. The recorded command preserves the supplied arguments and their order (with shell-safe quoting), including `--self`, relative paths and a bare `--codex-thread`. Omitted defaults stay omitted; no temporary state-directory path is injected. Restart it from the same project or directory context, with the appropriate harness identity. Rearming the same watch replaces its entry, including changed heads and flags. Different targets and signatures remain separate. Matching context is kept in a hidden `.BRIEF-FILENAME.waiter-context.json` file beside the brief so a later command from another directory or repository cannot replace the earlier watch. If that context is unavailable, ambiguous saved entries are preserved.

The entry survives one-shot events, interrupted waits, and delivery failures so it can be rearmed. `lemonaid watch stop --self` removes it along with the waiter it stops (see below); for a waiter that already exited, remove it with `lemonaid brief waiter rm --self "<unique command substring>"` when the watch ends permanently. The manual `add` and `set` verbs remain available for custom shell waiters. With no attached brief, watching works as before without recording; a failed write to an attached brief prevents startup and reports the error. Status queries, document edit markers, and refused duplicate waits never change the brief.

## Stopping your waiters

```bash
lemonaid watch stop --self              # every waiter you started
lemonaid watch stop --self pr 12        # one kind and target: a PR number, a path, a Lemon-ID
lemonaid watch stop --self inbox        # your `lemonaid inbox watch --self`
```

While it runs, each waiter (`inbox watch` and every `watch` kind but `openclaw`) keeps a file under `$LEMONAID_STATE_DIR/waiters/` locked. The file holds its pid, the channel of the lemon that started it, what it watches, and the command that rearms it. `stop` signals only waiters registered under the caller's channel whose file is still locked, so it never reaches another lemon's waiter or a process that has since reused the pid. It waits for each to exit, then removes the stopped waiters from the caller's `## Waiters`. Waiters started by lemonaid before 0.90.1 aren't registered; stop those by their task or pid.

A waiter stopped by SIGTERM, from `stop` or anything else, prints which waiter it was, who stopped it and the command that rearms it, then exits 143. Who is the lemon and pid that ran `watch stop`, or "a process outside lemonaid" for a `kill`, a `pkill` pattern or the harness; the lemonaid log records the same line. Never `pkill -f` a waiter command: the pattern matches every lemon's waiter on the machine.
