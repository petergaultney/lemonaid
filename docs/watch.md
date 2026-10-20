# Watching documents, PRs, repos, and files

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

A previously present document that stays missing for `--quiet` seconds produces a notice,
including with `--no-edits`. If a nearby path matches its last recorded filesystem identity,
the notice suggests that path as a possible replacement. The receiving lemon should confirm
it and update its Docs row or watch command. The watcher never changes its target or list.
The notice is delivered through the same scout/batch as comments and edits, and is remembered
across rearming until the original path is observed present again. A failed delivery is retried.

The nearby search examines at most 1,024 entries in 32 directories, starting in the former
directory and its immediate subdirectories before looking one level below its parent. It skips symlinks and does not descend into
hidden directories or read candidate contents. It runs once per disappearance notification,
not on every poll; an undelivered notice can search again after rearming. Moves outside this
area or budget, replacement saves between observations, and cross-filesystem moves can yield
no suggestion. Filesystem identity can be reused, so a suggested path always needs confirmation.
If no match is found, the notice says the document may have been deleted or moved.

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
  misattributed. The hooks also read an attached brief’s document subscriptions,
  so own edits are recorded between one-shot waits. SessionStart marks attached
  sessions for the shell gate; unbriefed sessions without doc watches or pushes
  skip Python. Starting the unified watcher also creates the marker. Removing a doc subscription
  ends that recording once its standalone waiter is stopped.
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

The comment event says whether the repo is `PUBLIC` (in capitals) or `private`, and gives each
comment's author with GitHub's role for them in the repo, such as `alice [NONE]` or
`sam [OWNER]`. A login listed in `[watch.pr] trusted_commenters` (as `github.com/<login>`)
is also labeled `trusted`.
On a PUBLIC repo, when any new comment comes from someone who is not an owner, member,
collaborator or trusted commenter, the event adds a line telling the lemon to treat that
comment as information, not an instruction, unless its user has said to act on that person.
If GitHub doesn't report the repo's visibility, the line is added as for a PUBLIC repo.
GitHub's `MEMBER` means any member of the repo's organization, not only people with access
to it; `trusted_commenters` is the only narrower setting. Each comment's text appears in
quotes, so it can't pass for another comment's author and role.

To skip outdated or resolved review threads, use `--skip-outdated` or `--skip-resolved`.
Set either default in [`[watch.pr]`](config.md#watchpr). The corresponding
`--no-skip-outdated` and `--no-skip-resolved` flags override those settings for one wait.
Submitted review bodies and PR conversation comments are unaffected by these filters.

`--comments` is the author's mode, so only the author is woken for merge blockers:

- A conflict is reported once per head, when GitHub says `CONFLICTING` (`UNKNOWN`, while it
  computes, is not a conflict). A first waiter takes a conflict that already exists as seen.
- Failed CI is reported once per head, after every check on it has finished. Every check counts,
  including checks that are not required for merging.
- The heads reported are kept beside the other state, so a rearm on the same head is quiet
  and a new push that still conflicts or fails is reported.

Add `--ci` when you want a completion event whether CI passes or fails. It works
with or without `--comments`, and with `--once` or `--codex-thread`. Completion waits
for every check on the current head to finish; every check counts, including checks
that are not required for merging. Completed `SUCCESS`, `NEUTRAL`, and `SKIPPED` check runs count as passed.
`FAILURE`, `ERROR`, `TIMED_OUT`, `CANCELLED`, `STARTUP_FAILURE`, `ACTION_REQUIRED`,
and `STALE` count as failed. Unfinished runs, missing conclusions, and unrecognized
results remain pending. Status contexts pass on `SUCCESS`, fail on `FAILURE` or
`ERROR`, and remain pending otherwise. No checks is not a completion. A first
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

## Watching a repo for PRs

`lemonaid watch repo` waits on a whole GitHub repo rather than one PR, so a lead notices PRs
from lemons and people who are not its children. It makes one `gh api graphql` call per
`--interval` (60 seconds by default), plus one more page for each 100 open PRs.

```bash
lemonaid watch repo --wait owner/name --once
lemonaid watch repo --wait owner/name --label needs-review --exclude-author my-bot --codex-thread
lemonaid watch repo --status owner/name
```

It reports, one line per event naming the PR's number, title, author and head branch:

- a PR opened ready for review (a new draft is remembered and reported when it is marked ready);
- a draft marked ready for review;
- a `--label` added to an open PR;
- a PR you have seen closed or merged, once (only the 30 most recently updated closed PRs are
  read, so more closings than that between polls leave the older ones unreported);
- with `--pushes`, a ready PR's head moving.

`--label NAME` (repeatable) limits every event to PRs carrying at least one of those labels,
compared without regard to case. `--exclude-author LOGIN` (repeatable) skips PRs by those
logins. "Tag" is read as a GitHub label.

The first waiter takes the PRs open now as already seen. The cursor (each open PR's draft
flag, head and labels) lives under the lemon's Lemon-ID like the other [cursors](#cursors), so
what changes between waiters is reported by the next one. One waiter per repo and lemon may
run; `--once`, `--codex-thread` and `--state-dir` work as in `watch pr`. As a `## Watching`
line it is read like `watch pr`, and its events join the batch. Stop it with
`lemonaid watch stop --self repo owner/name`.

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
- If a watched path itself disappears, its removal notice can suggest a nearby file or
  directory matching its last recorded identity, using the bounded search described above.
  The watch remains on the original path. `--ignore-removed` suppresses this notice and search;
  removals of children inside a watched directory retain the ordinary listing summary.
- A change is reported once it has been quiet for `--quiet` seconds (2 by default); paths
  are read every `--interval` seconds (5 by default).
- What was last reported is kept per set of paths in the lemon's [cursors](#cursors), so a
  rearmed waiter reports anything that changed in between. The first waiter for a set of paths takes their current state as its baseline.

## Watching other lemons

`### Lemons` in `## Now` lists lemons to watch besides your children. A row names a lemon
by Lemon-ID, channel or brief name:

```markdown
### Lemons

| Lemon | Purpose | Watch |
|---|---|---|
| `reviewer.SaltyEbb` | Reviews my PR | blocked, done |
| `other.WordyBin` | Owns the shared fixture | |
```

```bash
lemonaid brief lemon add --self reviewer.SaltyEbb --purpose "Reviews my PR" --to blocked --to done
lemonaid brief lemon set --self reviewer.SaltyEbb --to merge --to needs
lemonaid brief lemon rm --self reviewer.SaltyEbb
```

The Watch column lists the Statuses whose entry wakes you, plus `needs` for a change of
the lemon's Needs. Empty means `merge`, `done` and `needs`. Your direct children are
implicit rows with those defaults; an explicit row for a child replaces them. `brief
check` refuses unknown words, duplicate lemons and malformed tables.

Whatever the Watch column says, every watched lemon also reports, once per occurrence:

- Its harness exited (the SessionEnd hook recorded it, or no harness runs on its terminal).
- Its tmux session or its directory is gone, or no session is attached to its brief.
- It is deaf: idle with no inbox waiter for 60 seconds, as `lemonaid lemon doctor` derives it.

A report repeats only after the lemon was healthy (or had a different problem) in between,
so a second exit is a second report. A lemon whose brief is `done` is never reported, since
its session going away is normal, and one still waiting for its lemon to start is skipped.
A first watch, and a lemon newly listed in a row, takes the current state as seen.
A row whose lemon cannot be resolved is logged as a warning and not watched.

`watch --self`, `watch --self --status` and the push scout include these rows.
`watch briefs --children` reports the same liveness for children, and Status and Needs
changes as before.

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

When the calling lemon has an attached brief, `watch doc`, `watch pr`, `watch repo`, `watch file`, and `watch briefs` automatically record their restartable command in its final `## Watching` section after startup checks pass. With `--codex-thread`, the recipient thread’s attached brief is used instead of caller detection. The recorded command preserves the supplied arguments and their order (with shell-safe quoting), including `--self`, relative paths and a bare `--codex-thread`. Omitted defaults stay omitted; no temporary state-directory path is injected. Restart it from the same project or directory context, with the appropriate harness identity. Rearming the same watch replaces its entry, including changed heads and flags. Different targets and signatures remain separate. Matching context is kept in a hidden `.BRIEF-FILENAME.waiter-context.json` file beside the brief so a later command from another directory or repository cannot replace the earlier watch. If that context is unavailable, ambiguous saved entries are preserved.

The entry survives one-shot events, interrupted waits, and delivery failures so it can be rearmed. `lemonaid watch stop --self` removes it along with the waiter it stops (see below); for a waiter that already exited, remove it with `lemonaid brief waiter rm --self "<unique command substring>"` when the watch ends permanently. The manual `add` and `set` verbs remain available for custom shell waiters. With no attached brief, watching works as before without recording; a failed write to an attached brief prevents startup and reports the error. Status queries, document edit markers, and refused duplicate waits never change the brief.

## Stopping your waiters

```bash
lemonaid watch stop --self              # every waiter you started
lemonaid watch stop --self pr 12        # one kind and target: a PR number, a path, a Lemon-ID
lemonaid watch stop --self inbox        # your `lemonaid inbox watch --self`
```

While it runs, each waiter (`inbox watch` and every `watch` kind but `openclaw`) keeps a file under `$LEMONAID_STATE_DIR/waiters/` locked. The file holds its pid, the channel of the lemon that started it, what it watches, and the command that rearms it. `stop` signals only waiters registered under the caller's channel whose file is still locked, so it never reaches another lemon's waiter or a process that has since reused the pid. It waits for each to exit, then removes the stopped waiters from the caller's `## Watching`. Waiters started by lemonaid before 0.90.1 aren't registered; stop those by their task or pid.

A waiter stopped by SIGTERM, from `stop` or anything else, prints which waiter it was, who stopped it and the command that rearms it, then exits 143. Who is the lemon and pid that ran `watch stop`, or "a process outside lemonaid" for a `kill`, a `pkill` pattern or the harness; the lemonaid log records the same line. Never `pkill -f` a waiter command: the pattern matches every lemon's waiter on the machine.

## A brief's subscriptions

`lemonaid watch --self` runs one watcher for the lemon's attached brief. The brief
is the source of subscriptions; the watcher reads it again while running, gathers
pending changes into one message, delivers that message and exits. Handle the whole
message, then rearm. `lemonaid wait --self` remains a compatibility alias, sharing
the same lock, inbox and cursors.

### Declare what to watch

Here is a complete example. Replace the PR URL, paths and reply signature with yours.
`## Watching` goes last; `### PRs` and `### Docs` belong inside `## Now`.

```markdown
# Improve lemon notifications

Brief-ID: notifications.NoteBee

## Now

### Waiting on

- Review of the notification changes and replies to the design.

### PRs

| Work | PR | Review |
|---|---|---|
| Notification changes | [lemonaid#274](https://github.com/petergaultney/lemonaid/pull/274) | [review](~/notes/pr-reviews/notifications.md) |

### Docs

| Document | Purpose | Watch |
|---|---|---|
| `~/notes/design/notifications.md` | Discuss notification behavior | All edits |
| `~/notes/reports/notification-results.md` | Questions about the results | Relay comments |

## Goal

Implement and review the notification changes.

## Watching

- `lemonaid watch file --wait /tmp/notification-run.log --interval 1 --quiet 2`
- `lemonaid watch doc --wait ~/notes/pr-reviews/related.md --me 'Author (NoteBee)' --no-edits`
```

The rows and commands declare these sources:

| Source | What the unified watcher watches |
|---|---|
| `## Watching` | Supported `watch pr`, `doc`, `file` and `briefs` commands, using their supplied options. These are declarations, not shell commands to execute. |
| `### PRs` | Each PR with both comments and CI enabled, regardless of whether an explicit watch line omitted those flags. |
| A PR's Review cell | A local review document's unanswered comments. An explicit doc command or Docs row can also enable body edits. Obsidian links resolve through configured vault roots. |
| `### Docs` | Unanswered comments on each document; `Watch: All edits` also watches the body. Documents remain watched while the session exists, including when its brief says `Status: done`. |
| Inbox | Every pending message for this lemon, included in the same batch as source changes. |
| Children | Direct children entering `merge` or `done` or changing their Needs, using the existing child cursor, and any child whose harness exits, whose session or place is gone, or that is deaf or dead (see [Watching other lemons](#watching-other-lemons)). An explicit `watch briefs` line selects other statuses or orphan behavior. |
| `### Lemons` | Each listed lemon, child or not, like a child: its Status and Needs changes and its liveness. A row for a child sets that child's wake statuses. |

A repeated source is watched once. Explicit options are retained; a PR row forces
comments and CI on, and a Docs row with `All edits` enables edits. A closed or merged PR
is silent on first subscription; an existing subscription reports its closure once
and stops polling it.

The **Watch** column is an enum, not a boolean. Its current values are:

- **Relay comments:** unanswered Relay comment threads only.
- **All edits:** Relay comments and body edits, after the document’s quiet period.

The inbox viewer makes document paths clickable, even in backticks. Vault
documents open through Obsidian links; other paths use file URLs and the system
opener (for example, HTML files open in the configured browser). Generated rows
contain explicit links, and manually written path cells are linked in the viewer.
The viewer displays a short filename label, keeps the full target in its tooltip,
and reserves enough table width for both Watch modes. Wrapped labels remain
clickable on every line.

New modes can be added to this enum. `Edits` columns and boolean values are not
accepted. An add/remove operation refuses to rewrite an invalid Docs table,
preserving every existing row until the table is corrected. The command defaults
to `Relay comments`; select the other mode with
`--watch "All edits"`.

### Maintain the brief

```bash
lemonaid brief watching add --self "lemonaid watch file --wait /tmp/notification-run.log --quiet 2"
lemonaid brief watching rm --self "notification-run.log"
lemonaid brief doc add --self /path/to/design.md "Discuss the design" --watch "All edits"
lemonaid brief doc add --self /path/to/results.md "Questions about the results"
lemonaid brief doc rm --self /path/to/results.md
lemonaid brief pr add --self https://github.com/owner/repo/pull/274 "Notification changes" --review /path/to/review.md
lemonaid brief check --self
```

New briefs and templates use `## Watching`. Legacy `## Waiters` headings and
`brief waiter` edit verbs still work. A backticked watch command can have a note
after its closing backtick. Starting a standalone watch records its subscription;
starting `watch doc` also records its Docs row. `Output-Doc:` supplies a document
subscription when the document is not already in the table. `brief check` warns
about linked vault documents without Docs rows.

### Arm, handle a batch, rearm

Read the current PR, documents and work before your first arm: watching reports
changes, rather than replacing that initial inspection.

```bash
lemonaid watch --self --status
lemonaid watch --self                        # Claude without a push scout: a background Bash task
lemonaid watch --self --codex-thread         # Codex: escalated exec_command session
```

A Claude lemon whose `--status` says `push scout running` is already watched (see
below). A Claude lemon without a scout runs the command with `run_in_background` and
`timeout: 2147483647`; task completion wakes the turn. For Codex, use bare
`--codex-thread` in an escalated session so `codex queue` can write to the thread. The
command refuses to start if Codex delivery is unavailable. Do not start another watcher
while `--status` says one is running.

The unified command accepts:

| Flag | Meaning |
|---|---|
| `--self` | Select the attached brief and unified watcher. |
| `--channel CHANNEL` | Override caller identity outside normal harness detection. |
| `--status` | Check the shared lock: exit 0 when running, 1 when absent. |
| `--codex-thread [THREAD_ID]` | Deliver into Codex; bare means the current thread. |
| `--interval SECONDS` | Brief/inbox read interval, default 0.5. |
| `--quiet SECONDS` | Batch gathering quiet period, default 2. |

A normal run exits 0 after successful delivery or detachment; exit 2 means startup
or identity setup failed, 3 means another watcher already holds a required lock,
and 1 means a delivery/read failure left changes for the next arm. A forced stop
still follows the registered-watcher stop behavior described above.

A batch can look like this:

```text
[pr: petergaultney/lemonaid, 274] PR #274 head moved aaaaaaaa -> bbbbbbbb; PR #274 CI passed at bbbbbbbb

[doc: /path/to/design.md] 2 new or changed unanswered thread(s) in /path/to/design.md (2 unanswered in all); Sam: clarify the defaults; Reviewer: check the migration

[inbox] From: another-lemon.MovieLay
Sent: 2026-10-14T13:00:00+00:00

The review is ready.
```

Read every changed source, answer all pending document threads and act on the
inbox messages, then run the same unified command again. An unchanged unanswered
thread does not create a fresh wake on every rearm. The session may remain idle
with the watcher armed; it does not need repeated model turns to poll.

`--interval` controls brief and inbox reads (default 0.5 seconds). `--quiet` controls
batch gathering after the last event (default 2 seconds). Individual watch commands
keep their source polling and quiet options. Documents wait for their own quiet
period, normally 20 seconds, before reporting a body edit. A new comment waits only
until the file has been unchanged for 3 seconds, and the event lists all unanswered
threads together. A document
still being edited holds back only its own event; other ready sources can deliver.


### The Claude push scout

A Claude lemon's scout is a detached process that keeps watching instead of exiting: it writes each batch
into the Claude session through the session's inbox socket (listed in
`~/.claude/sessions/<pid>.json`), saves cursors only once the socket has taken the batch,
and exits when the session ends or its brief is detached. It holds the same lock as
`watch --self`, so a second one for the same lemon refuses to start, and the Stop check
counts it as the lemon's watcher.

The SessionStart hook, the Stop check and `lemonaid tell` each start one when the lemon
has none and its session would read a pushed message, and so does the live inbox for a
Claude lemon it marks `deaf` (at most once a minute per lemon). A lemon whose `--status`
says `no watcher running` can start its own with `lemonaid watch --self --push`, which
returns at once; starting one where a watcher already runs does nothing. The scout's
output goes to `push-scout.log` in the state directory. When the session
would hold the message (bypass-permissions mode without `"crossSessionInbound": "accept"`,
see [Claude setup](claude.md#3-let-lemonaid-push-events-into-each-lemon)), nothing starts
and the lemon falls back to a background `watch --self`. If the socket refuses a batch, the
scout exits and the batch stays pending for the next watcher.

Each scout logs `push scout started` and `push scout exited normally` or `exited
abnormally` to the lemonaid log, with its Lemon-ID, session and pid. A normal exit is
its session ending, its brief being detached, or `lemonaid watch stop`. A refused batch,
a crash, or a SIGTERM that `watch stop` didn't send is abnormal and logged as a warning.
A start line with no exit line is a scout that was killed outright.

### Cursors, delivery and recovery

- **First arm:** take the source's current state as seen, including already completed CI. Unanswered document comments are the exception: they are reported on first arm.
- **Between arms:** per-lemon cursors remember delivered changes, including edits and pushes while no watcher ran. An explicit PR `--head` seeds a missing cursor; it does not override a saved head on each rearm.
- **Successful delivery:** advance event cursors and move delivered inbox messages to `done/` only after delivery succeeds. Source detector threads wait for that acknowledgement.
- **Failed delivery:** keep inbox messages and event cursors pending so the next arm can deliver them. No event is acknowledged merely because it was detected.
- **Brief edits:** add or remove subscriptions without restarting. Each invalid line or table error is reported once while valid sources keep running; an incomplete brief write retains the previous readable list. Custom shell commands are not executed.
- **Source failures:** persist the reported failure across rearms and clear it when the source recovers. GitHub failures are reported after three in a row, rather than every failed fetch, and each one doubles the wait before that subscription's next read, up to 10 minutes. When GitHub refuses a read for quota, or reports fewer than 100 points left, every GitHub read on the machine pauses until the reset GitHub names, recorded in `$LEMONAID_STATE_DIR/github/paused-until.json`. Each lemon is told once, with the resume time, and no "Cannot reach GitHub" notice is sent for it.
- **Document changes during batching:** discard a stale pending doc event and reread it. Missing or deleted documents do not kill the whole watcher.
- **Own changes:** installed own-change hooks suppress recorded edits and pushes by this lemon. Attached Docs and Watching documents are considered between arms too. Tool input must name the edited file. SessionStart and the unified command maintain the cheap per-session shell gate; unbriefed sessions without doc registrations or pushes skip Python.

Cursors live under `~/.local/state/lemonaid/cursors/<Lemon-ID>/`. The unified command
uses the existing detector cursors where their source and options match, including
the default direct-child cursor. Deleting cursors loses that history. Own-change
records live separately under `~/.local/state/lemonaid/own-edits/`.

There is one unified lock per lemon. Codex's inbox delivery service yields while
it is held so it cannot deliver the same inbox batch independently. A Codex rearm
waits briefly for a holder that has already delivered to finish saving its cursors;
all post-delivery joins share one deadline.

### Migrate and stop

Stop separately running watchers before switching, while preserving their declarations:

```bash
lemonaid watch stop --self --keep-subscriptions
lemonaid watch --self --status
lemonaid watch --self --codex-thread          # Codex only; a Claude push scout needs no arming
```

The SessionStart hook tells attached lemons to read current work and arm the unified
watcher. The Stop hook, for Claude and Codex, requires it when the brief has subscriptions;
a separate inbox-only watcher is insufficient. Legacy inbox-only Claude waiting remains
accepted for a brief without other sources.

After upgrading the installed tool, run `lemonaid hooks install` to replace older
hook commands; trust changed Codex hooks again in `/hooks`. This PR does not install
or edit the maintainer's live hook settings. `lemonaid skills install` updates the
packaged guidance (see [Skills](skills.md)).

To end watching:

```bash
lemonaid watch stop --self
```

Stopping running watchers and removing a subscription are different operations.
Remove Docs rows and Watching lines explicitly when their conversations have ended;
stopping a process alone does not erase a Docs or PR table subscription. Keep document
subscriptions while the session exists, even after its work is done. Standalone
`watch doc|pr|file|briefs` commands remain available; OpenClaw's persistent session
watch lists remain a separate workflow.
