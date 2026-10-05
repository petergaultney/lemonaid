# Lemonaid for Lemons

Programmatic access to lemonaid for LLMs and other automated tools.

Print this guide from anywhere with `lemonaid for-lemons` — it ships with the package, so you
don't need to know where a checkout lives. Every command below also has `--help`.

## Inbox Commands

### List notifications

```bash
# List all unread notifications as JSON
lemonaid inbox list --json
```

Output:
```json
[
  {
    "id": 42,
    "channel": "claude:abc123",
    "name": "my-session-name",
    "message": "Permission needed in my-project",
    "metadata": {"cwd": "/path/to/project", "tty": "/dev/ttys001", "session_id": "abc123..."},
    "status": "unread",
    "created_at": 1768578211.645825,
    "read_at": null,
    "switch_source": "tmux"
  }
]
```

### Get a specific notification

```bash
lemonaid inbox get 42 --json
```

Returns a single notification object, or `null` if not found.

### Mark as read

```bash
lemonaid inbox read 42
```

A session whose turn ends with a final message matching the user's `[inbox] auto_read`
patterns is marked read automatically. `lemonaid for-lemons` lists this machine's patterns
at the end of this guide.

### Add a notification

```bash
lemonaid inbox add "channel-name" "Title" -m "Optional message" --metadata '{"key": "value"}'
```

### Emoji and display name

Both are decoration on one harness session - the Claude session or Codex thread you are,
not your place or tmux session. Neither changes your name for signing and watching, nor the
tmux session name.

When the user asks you to set an emoji, pick one yourself: see which are taken, choose one
that fits your work, and set it without asking them which.

```bash
lemonaid inbox emojis --json                 # emojis live sessions already hold
lemonaid inbox emoji --self 🦫               # shown before your name in the inbox
lemonaid inbox emoji --self --clear
lemonaid inbox rename --self "tenant views"  # your inbox display name
lemonaid inbox rename --self --clear         # back to the backend's name
```

- Every target resolves to one channel (your backend session id) before anything changes,
  so the emoji and name survive compaction and `--resume`. A fresh lemon starts without one.
- `--self` takes your session from your harness's environment (`CLAUDE_CODE_SESSION_ID`,
  `CODEX_THREAD_ID`, or `LEMONAID_CHANNEL`), so it works inside the Codex sandbox, where tmux
  can't be asked. Without those it looks up the live session recorded at your pane's tty, tmux
  session, and window, and refuses, rather than guessing, when none or several match - for example before your
  harness has sent lemonaid a notification, or when the recorded location is out of date.
  Then name yourself explicitly with `--channel <channel>` or `--id <n>`, from
  `inbox list --json`, or by `--lemon <Lemon-ID or brief name>` once a brief is attached.
- An emoji another live session holds is refused. Snoozed sessions count as live; an
  archived session keeps its emoji but no longer holds it.
- The rename is the same override the TUI's rename key sets.

`inbox emojis --json` prints `[{"emoji", "id", "channel", "name", "cwd"}]`. `rename` and
`emoji` take `--json` and print `{"channel", "name"}` or `{"channel", "emoji"}`, plus
`"error"`.

### Snoozing yourself

`inbox snooze` holds your row out of the user's active inbox until a time, as the TUI's `s`
key does. It takes the TUI's syntax: a duration (`45m`, `2h`, `3d`, `1w`; a bare number is
minutes) or `morning`. Days and weeks count mornings at `[inbox] snooze_day_starts` (09:00
unless set): `1d` and `morning` end at the next one, `3d` at the third. It takes the same targets as `rename` and `emoji`.

```bash
lemonaid inbox snooze --self 2h
lemonaid inbox snooze --self morning
lemonaid inbox snooze --self --clear   # back in the inbox now
```

- The snooze lasts through the end of your turns, including the one you set it in. A turn
  that ends while you're snoozed updates your row but leaves it snoozed.
- When it wakes, your row comes back unread if any of those turns ended unread, and read
  if every one matched `[inbox] auto_read`.
- A permission prompt or a question wakes it at once. So does the user, from the TUI's
  snoozed list (`S`).
- If a later turn has something the user should see now, run `--clear` before you end it.
- Snoozing again moves the wake time. An archived session is refused.

`--json` prints `{"channel", "snooze_until", "wakes", "woke", "error"}`: `snooze_until` is
epoch seconds, `wakes` the same time as local ISO, and `woke` whether `--clear` woke a
snoozed row.

## Notification Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique identifier |
| `channel` | string | Source identifier (e.g., `claude:<session_id_prefix>`) |
| `name` | string? | Session name (from Claude Code or derived from cwd) |
| `message` | string | Status text (e.g., "Permission needed in my-project") |
| `metadata` | object | Arbitrary JSON metadata (cwd, tty, session_id, etc.) |
| `status` | string | `unread`, `read`, or `archived` |
| `created_at` | float | Unix timestamp |
| `read_at` | float? | Unix timestamp when marked read |
| `switch_source` | string? | Switch-source: `tmux`, `wezterm`, `cmux`, or `null` (determines which switch-handler can navigate back) |

Inside tmux, `metadata` also carries `tmux_session`, `tmux_window`, and `tmux_socket` — where the
session was running and on which tmux server, so a lost tmux server can be rebuilt from the inbox. All
are absent when the hook ran outside tmux, and a later observation that can't see tmux does not erase
them.

Inside cmux, `metadata` carries `cmux_surface`, the surface the session ran in, kept the same way.

## Restoring a lost tmux layout

```bash
lemonaid restore tmux --dry-run --json   # what would be rebuilt, and which lemons get a prompt
lemonaid restore tmux --json             # {"restored": [...], "skipped": [...], "lemons": [...]}
```

`lemonaid tmux restore` is the same command. It recreates the tmux sessions the active inbox says its
lemons were running in, resuming each in the window it occupied, and starts each lemon whose brief lists
waiters with a prompt to rearm them. It then waits up to `--wait` seconds and reports each lemon's
`outcome`: `working`, `stuck`, `exited`, `no brief`, `nothing to rearm`, `rearm by hand` (an OpenClaw or
opencode lemon whose brief lists waiters: only Claude and Codex take a prompt on resume), or `not
restored`, with a `detail` from its pane for the ones that need a hand. It exits 1 for any outcome but
`working`, `no brief`, and `nothing to rearm`. Windows keep their recorded index, so one lemonaid knows nothing about comes back as
an empty gap rather than shifting the others down.

Sessions already running are left alone, so this is safe to re-run. A session with no recorded location
can't be placed and is skipped — check `--dry-run` before assuming a session will come back.

```bash
lemonaid tmux doctor            # coverage, restorability, hook state
lemonaid tmux doctor --unknown  # running panes with no inbox row
```

`doctor` is what to run before relying on any of this. A session whose transcript is gone still looks
restorable, and `claude --resume` on a missing id starts a fresh conversation without reporting an
error — so the failure presents as success. `doctor` names those first.

## Recording sessions that haven't spoken

```bash
lemonaid claude hooks           # install the SessionStart hook
lemonaid claude hooks --dry-run
```

Every other Claude hook needs a user turn, so a session nobody has talked to yet is not in the inbox at
all — and those are exactly the ones a restore has to find. `SessionStart` fires on startup and on
resume, recording the session and its current location without a turn.

Sessions register as working, never unread. Installing is additive and idempotent; hooks you did not
write are never touched.

## Places

A **place** is a directory you work in. lemonaid knows about directories and terminals — it
does not know what a git worktree is, or any other scheme for organizing directories.

How directories get acquired and released is declared per-repo-root in
`~/.config/lemonaid/config.toml`. **Ask, rather than assuming:**

```bash
lemonaid place hooks --json
```

That prints the actual commands configured on this machine, e.g.:

```json
[{"path": "/home/me/work/somerepo",
  "list": "git -C .bare worktree list --porcelain | ...",
  "path_of": "wt path {key}",
  "create": "wt co {key}",
  "destroy": "wt rm -f {key}",
  "inspect": "wt status {dir}"}]
```

Read it before creating or removing a directory in a configured root, and use the tool it
names. A root with empty hooks is a plain clone with nothing to acquire or release.

`{key}` is whatever the configured tool names directories by — for a git-worktree tool, a
branch name. lemonaid does not interpret it.

### Just needing a directory

**This is almost always what you want.** You have your own session, you are not a tmux
client, and you will never attach to one.

```bash
lemonaid place acquire <key> --json   # {"key", "dir", "root", "error"}
lemonaid place acquire <key>          # just the directory, one line
```

Runs the root's `create` hook if the directory doesn't exist, prints where it is, and creates
no tmux session. Idempotent: an existing directory is printed rather than re-created, and
that is not an error, so don't check first.

Nothing is recorded when a directory is acquired. Ownership is worked out from tmux at the
moment it's asked, so a directory acquired this way, made by hand, or opened as a place are
indistinguishable afterward — `place list` reports all three and `place toss` releases all
three.

### Getting a session for a place

Only when a session is genuinely wanted — the user asked to be taken somewhere, or asked you
to set a place up for them to attach to later.

```bash
lemonaid place open <key> --json           # acquire if needed, then open a session
lemonaid place open <key> --detach --json  # ... without stealing the terminal
lemonaid place open <key> --harness codex --prompt 'read .z/brief.md' --json
```

Idempotent: the directory is acquired only if it doesn't exist, its session is switched to
only if there isn't one, and neither case is an error. Always safe to run without checking
first, so don't probe for existence beforehand. `--json` returns
`{"key", "session", "dir", "root", "brief", "lemon_id", "parent", "error"}`, where
`session` is the tmux session opened or switched to.

`--detach` still creates the session, it just doesn't switch to it — so it is not the polite
way to acquire a directory. Use it when a session is wanted but the terminal shouldn't move.
An unattached session nobody asked for is worse than no session: it clutters the session
list and competes for the directory when something later tries to resolve who works there.

`--harness NAME` selects `[tmux-session.templates].NAME`, named for the harness
it starts (`--harness claude`, `--harness codex`); omitting it selects the
template `default` names. Commands are config-owned — Lemonaid does not hardcode how Claude,
Codex, or another harness starts. `--prompt TEXT` reaches the command in
`harness_window` (falling back to `resume_window` when that setting is absent) as
one positional argument, through the window's environment, so any text is safe
in any shell. Both options matter only
when `open` creates the session. If a session already exists, `open` switches to
it without starting another harness or sending the prompt.

A template line whose program is `codex` also gets `-c` overrides that trust the
directory and skip the update check, so Codex reads its prompt instead of stopping
at a dialog. Nothing is written to `~/.codex/config.toml`.

With `--prompt`, a new session's harness window is checked once, a few seconds after
it starts. If the lemon is stuck at a startup dialog (Claude's folder-trust prompt has
no override), `open` fails with `"error": "Opened, but the lemon in <session>:<window> is
waiting at ..."`. The session and any `--brief` are still set up, and the brief attaches
once someone answers the dialog. `--no-check` skips the wait.

The tmux session is named after the key (with `.` and `:` replaced, since tmux forbids them),
so `tmux send-keys -t <key>` and similar work afterward. `place list --json` reports the
actual name.

Acquiring a directory can take minutes — it may install dependencies. Don't set a short
timeout and don't retry on a timeout; a second call would just wait on the same work.

### A lemon in another window: `lemon start`

To start a lemon in a window of a session that already exists (a reviewer in window 4, or a
lemon whose window died), use `lemon start` rather than typing a launch line into a pane:

```bash
lemonaid lemon start <session>:4 --harness codex --prompt 'REVIEW #12. Instructions are in <file>; follow them.' \
    --brief <file> --parent self --name 'REVIEW #12 thing' --json
```

It runs the same template line `place open` runs in its harness window, in the session's
directory. The window is made if it doesn't exist and respawned if its panes are dead; a window
with anything running in it is refused. `--brief`, `--parent` and `--name` work as on
`place open`: the brief and the name go to the first new lemon in that window. Afterwards it
checks the pane once and fails if the lemon is stuck at a startup dialog; `--no-check` skips
that. `--json` returns `{"session", "window", "window_id", "dir", "harness", "brief",
"lemon_id", "parent", "name", "error"}`.

### A session where there is no place

Run from a directory no configured root manages the names of, there is no key to resolve,
so the name is simply a session opened in the current directory. Nothing is acquired, and
the JSON reports `"root": null`.

```bash
cd ~/somewhere-unmanaged && lemonaid place open notes --json
# {"key": "notes", "dir": "/home/me/somewhere-unmanaged", "root": null, "error": null}
```

There is no directory to acquire here, so this command is only ever worth running when a
session is the point.

This is not a fallback for a key that failed to resolve. Inside a root with a key
vocabulary the name is always a key, and a name that doesn't resolve is acquired — so a
mistyped key creates a directory rather than a bare session. Check `place hooks --json` if
you need to know which roots have one: a root with no `list` and no `path_of` claims no
names.

Identity here is the name, not the directory, so several differently-named sessions in one
directory are fine. `place list` does not report these — they are sessions, not places.

### Listing places

```bash
lemonaid place list --json
```

Every directory each root reports, whether or not it has a session:

```json
[{"root": "/home/me/work/somerepo",
  "dir": "/home/me/work/somerepo/release/202608",
  "key": "release/202608",
  "session": "release/202608"}]
```

`key` is what to pass to `open` and `toss`. `session` is the live tmux session name, or `""`
when nothing is running there — which is how you tell an idle place from an active one.
If a root's hook reports a directory outside that configured root, it is skipped
and logged rather than aborting the entire listing; it has no key in that root's
namespace.

### Tearing one down

```bash
lemonaid place toss <key> --json
```

**The unit is the place.** Its directory is released, and the tmux session sitting in it
closes too when that session is *dedicated* to the place: named for it (what `place open`
makes), or entirely inside it, and holding no other managed place. The response says what
happened:

```json
{"session": "feat/base", "released": ["feat/base"], "error": null,
 "place": "feat/base", "closed_windows": ["@1", "@2", "@4"], "session_closed": true}
```

A session that also holds other places is shared: only its windows that sit in the place
close, and the session stays (`"session": ""`, `"closed_windows": ["@4", "@7"]`). A window in
any other unprotected session that sits in the place closes too. A window with a pane in the
place and a pane elsewhere refuses, naming both panes. The plan is made again from a
fresh look at tmux right before anything closes, and any difference (a pane that moved, a
window split or opened in the place, a session that gained a window) stops the whole toss
(exit 1, nothing closed, nothing released); run it again.

**Always pass the key.** Named, it works from anywhere. The unnamed form acts on the place
the current directory is in, and refuses when that directory is not a listed place (outside
every root, or under a root with no `list` hook). It never falls back to the tmux session
you are in. Under `--yes` or `--json` it also refuses to close the session the command runs
in, or one it cannot tell apart from it (no `TMUX_PANE`): a lemon tearing down its own
session names it, `place toss <key> --json`.

**`--json` implies `--yes`**, so it does not prompt. It still refuses when the root's
`inspect` command reports uncommitted or unpushed work; `--force` overrides that. **Do not
pass `--force` on a user's behalf without being asked to** — it is the difference between
tearing down unattended and discarding work.

Two kinds of protection, and `--force` overrides neither:

- A root's `protected` keys (`main` and `master` by default) are never released and never
  count as held, so a window in the trunk worktree does not make a session shared.
- `protected_sessions` under `[places]` refuses teardown of that session entirely. Naming a
  place it occupies is not a way around it.

A place with no session — an `acquire`d directory nobody opened — is just released
(`"session": ""`, `"session_closed": false`, `"closed_windows": []`). A window in a
protected session that sits in the place is never closed; the confirmation lists it as
staying open, in a released directory.

Teardown finishes after the command returns — releasing a large directory is slow, so it
runs detached. Its output goes to `~/.local/state/lemonaid/reap.log`.

## Briefs

A brief is a Markdown file describing one unit of work, attached to the lemon session doing it:
one Claude session or Codex thread, found by its inbox channel. Its `Lemon-ID` belongs to the
work, not the session, and stays the same across brief renames and session changes. An author
and reviewer sharing a place each have their own brief. Briefs live in
`~/.lemons/brief/<YYYY-MM-DD>-<slug>.md` (`~/.brief-lemons/` on an install not yet migrated; see
`docs/home.md`), never in the repo.
A brief is how a parent hands a lemon its task, and how that lemon reports where the work stands.

```bash
lemonaid brief new --self "Fix the thing"      # create ~/.lemons/brief/<today>-fix-the-thing.md, attach it
lemonaid brief new --child "Fix the thing"     # create it for a lemon not started yet; see Child briefs
lemonaid brief attach --self <file>            # attach an existing one (relative names are in ~/.lemons/brief/)
lemonaid brief attach --session work:4 <file>  # on another lemon's behalf; the window picks one of several
lemonaid brief id --channel <channel>          # print the stable ID stored in its brief
lemonaid brief id --self --reroll              # new random WordyBin; the old ID keeps working (--set QuickOdd picks one)
lemonaid brief status --self waiting            # Status: waiting  (working | running | waiting | blocked | merge | approve | review | alert | done)
lemonaid brief bullet add --self "Next" "open the PR"       # under ### Next; Done adds at the top
lemonaid brief bullet set --self "open the PR" "PR #12 open" # replace the one bullet starting with that text
lemonaid brief bullet rm --self "PR #12"                     # remove it; an emptied heading goes too
lemonaid brief pr add --self <url> "Delivery service" --review <vault doc>  # a row in ### PRs
lemonaid brief pr rm --self 12                 # by number, or by URL when two repos share it
lemonaid brief waiter add --self "lemonaid watch pr --wait 12 --head a1b2c3d --once"  # a bullet in ## Waiters
lemonaid brief waiter set --self "wait 12" --head e4f5a6b  # rearm: the same waiter on a new head
lemonaid brief waiter set --self "wait 12" "<command>"  # or replace its whole command
lemonaid brief waiter rm --self "wait 12"       # remove the one waiter whose command contains that
lemonaid brief check --self                    # what is wrong with the brief; exit 1 if anything is
lemonaid brief check --all                     # every brief of a session that isn't archived
lemonaid brief now --self "### Next ..."       # replace all of ## Now (- reads it from stdin)
lemonaid brief detach --self                   # the file stays
lemonaid brief list --json                     # every brief file and the session it belongs to
lemonaid place open feat/thing --brief <file>  # attach to the first lemon that starts in the new session
lemonaid place open feat/thing --brief <file> --parent self  # and record yourself as its parent
lemonaid lemon children --self --json          # your children, with their brief Status:
lemonaid brief children --self                 # your children's places, sessions, PRs, and cleanup
lemonaid brief handoff --to codex               # replace this harness in its tmux pane
lemonaid brief handoff --to claude --brief FILE # request a handoff for another lemon's brief
lemonaid brief handoff status TOKEN             # phase, channels, missing check, exact user phrases
lemonaid brief handoff ready TOKEN              # outgoing lemon's explicit acknowledgement
lemonaid brief handoff accept TOKEN             # incoming lemon's explicit acknowledgement
```

Parent links are between Lemon-IDs; see `docs/lineage.md`.

### Harness handoff

`brief handoff --to claude|codex` needs an attached brief and a live outgoing
inbox row. It sends the outgoing lemon a request with a random token.
The outgoing lemon writes a fresh `## Handoff` section with at most five bullets,
using its current brief without rereading files when that brief is already current.
It stops its waiters and ends that section with `Handoff-Ready: TOKEN` on its
own line. If the outgoing
harness is Claude, the same standalone line in its completed final reply also
counts. Lemonaid checks the file is stable and passes `brief check` in either
case. With a live tmux pane, it first checks that the outgoing session has a
usable resume command. It then replaces the outgoing process in that exact
pane with the configured target harness. The pane and window IDs do not change.
The new lemon reads the brief, rearms the waiters, and runs
`brief handoff accept TOKEN`. This tmux replacement ends the old process
immediately after the handoff passes readiness; its session can be resumed by
the original session ID if needed.

If the outgoing session has no live tmux pane, status instead prints a
`start_command` and `start_prompt` once readiness passes. Run the command in a terminal to start
the destination harness in the outgoing working directory. It uses the configured
harness template's command when present, or `claude`/`codex` if no template is
configured. To keep the same plain terminal window, exit the outgoing harness
after readiness, then run `start_command` in the shell that returns in that
window. It passes the token
to the new harness and prompts it to read the brief, rearm waiters, and accept.
In a desktop or remote-control app, open the destination session using its UI
and give it `start_prompt`; same-window placement depends on that app. Manual
`accept TOKEN` must run inside that harness with its own session ID; the token
is required, and an inherited token must match if present. The handoff waits
for the target inbox row before transferring state.
If a manual launch fails or the handoff times out, the source keeps the brief.
Status includes `resume_command` built from the outgoing session's configured
resume command. Run it in the same terminal, then rearm the old waiters before
making a new `--to` request.
Lemonaid cannot replace a desktop app's process or force a remote-control app
to reuse a particular window. Its manual mode provides the prompt and command
for the app or terminal to run sequentially.

While a handoff is pending and unexpired, Claude's Stop hook allows the outgoing
session to stop its inbox waiter. Brief validation still runs. If the handoff
fails before replacement, the usual waiter requirement returns and lemonaid
prompts the outgoing Claude in its original pane to rearm. After replacement,
tmux retains the pane if the target exits. A target exit or acceptance timeout
resumes the original harness in that pane using its configured resume command.
If another process has taken the pane, status reports that manual recovery is
needed rather than replacing that process.

The command prints JSON with a durable token and phase. `brief handoff status TOKEN`
reports what is still missing and can resume coordination after an interruption.
Concurrent status calls and the background coordinator serialize work for that token,
so they replace the outgoing process only once.
Handoffs into Codex also work when the outgoing working directory has Unicode
characters in its name.
The outgoing or incoming user can instead type the whole message
`lemonaid handoff ready TOKEN` or `lemonaid handoff accept TOKEN` in the respective
harness. Claude's submit hook and the Codex transcript detect these messages.
The CLI `ready` and `accept` verbs use the same checks if prompt detection is
unavailable. A ten-minute deadline stops automatic coordination. A failed
handoff releases the brief for a new request after the source is resumed.

After both acknowledgements, one transaction moves the brief and manual inbox
state. The new channel retains its own notification and session metadata. The old
channel is archived. The replacement remains in the original pane and window.
The pane's previous exit setting is restored after a successful transfer.
An active snooze on the old channel carries over, including its wake time and
through-turns setting. A real outgoing session title carries over if the new
channel still has a placeholder title; a title supplied by the new harness wins.
Both backend transcripts and session IDs stay intact; resuming the old backend
session by its original ID reclaims the brief and manual state without stopping
the replacement session.

### Children and their cleanup

`brief children --self` lists each of your children, with its own children (its reviewers)
nested under it:

- its Lemon-ID, display name, `Status:` and how long it has held it, and when its brief was last
  edited. The time in a Status counts from when lemonaid first saw it, as on a `waiting` card
- its place's key and directory, and whether the directory still exists. Under a root with no
  `list` hook, lemonaid can't enumerate places, so it reports the shallowest directory below the
  root that the child's session or lemon sits in, marked `unlisted`
- its tmux session, whether that session is alive, and how many clients are attached
- the PRs in its `### PRs` table
- `cleanup`: `ready` when it and every descendant say `done` and no client is attached to any
  of their sessions. `orphan` when it isn't `done` but its session is gone, which usually means a
  lemon that stopped without finishing its brief. `cleaned` when it is `done` and neither its
  session nor its directory is left. Otherwise `held`, with what holds it up.

A child whose brief says `done` is left out once its directory is known to be gone; `--all`
shows it anyway. One whose place lemonaid couldn't find stays in.
`--json` gives the same tree, with the reasons in `held_by`.
`ready` says nothing about the branch. lemonaid knows nothing about git, so before you tear a
place down, check yourself that its work is on the trunk.

### Child briefs

A parent writes its child's brief with `brief new --child`, which attaches it to no one and
prints the path to pass as `--brief`:

```bash
f=$(lemonaid brief new --child "Fix the thing")   # ~/.lemons/brief/<today>-fix-the-thing.md
lemonaid place open feat/thing --brief "$f" --parent self --prompt "Fix the thing. Instructions are in $f; follow them."
lemonaid brief new --child --template review --pr https://github.com/o/r/pull/12 \
    --review-doc ~/notes/reviews/r-12.md --slug review-r-12 "Review r#12: the thing"
```

The file has the title, its own `Lemon-ID:`, `Status: working`, and `Parent: <your Lemon-ID>
(<your tmux session>), <date>`, then the template's sections. It has no `## Now`; the child
writes that. `--parent` names a parent other than yourself (a Lemon-ID, channel, or brief).
`--area apps/unified-asset` adds an `Area:` line naming the part of the project the work is
in; brief cards show it after the project (`ds-monorepo: apps/unified-asset`). A worker
without one can add the line itself, anywhere above its brief's first `##` heading.
`--slug` replaces the title's slug in the filename. An existing file is never overwritten.

A template is the brief's body, from `## Goal` down, with `$name` placeholders (`$$` is a
literal `$`). Lemonaid packages two:

- `child` (the default): empty `## Goal`, `## Context`, `## Limits`, `## Output` and `## Waiters`.
- `review`: a cross-harness review of `--pr` (a URL, or a number with `--repo owner/name`), with
  findings only in the `--review-doc` (linked into Obsidian when it is under a `[brief] vaults`
  root), the rule to stay `waiting` until the PR merges or closes, a `lemonaid tell` to the parent
  and `--author` when it is someone else, and the `watch pr` and `watch doc` waiters signed with
  the child's WordyBin. Fill in `## Context` yourself.

A file in `~/.lemons/brief-templates/<name>.md` replaces the packaged template of that name, or
adds a new one. Placeholders: `$title`, `$date`, `$lemon_id`, `$wordybin` (the child's),
`$parent_id`, `$tell`; with `--pr`, `$pr_url`, `$pr_number`, `$pr_repo`, `$pr_label` and
`$pr_link`; with `--review-doc`, `$review_doc` (absolute), `$review_doc_arg` (shell-quoted) and `$review_doc_link`. A template
that uses a value whose flag is missing is refused before any file is written.

`--self` is the calling lemon, resolved the same way as `inbox emoji --self`.
`--channel <channel>` or `--id <id>` names a session by its inbox channel or row. `--session SESSION:WINDOW` naming a window no lemon has started in yet
waits for the first lemon live there that wasn't live when the brief was attached, including one
resumed from the archive; this is also what `place open --brief` does. The window is an index or a
tmux window name, and it is followed if tmux renumbers it. A lemon already running there that
the inbox hasn't placed in the window yet gets the brief once it is. A Codex on the shared
app-server is never placed, so for one of those the command fails and asks for `--channel`. Every command
takes `--json`.

`brief status` takes only the state and writes one word after `Status:`. Put notes in `## Now`
with `brief bullet`. Readers still recognize older `Status: done - PR #12` lines as `done`.
Use `review` when the next move is a teammate's approving review rather than your user's; say whose
under `Needs`, which its card shows as it does for `blocked`.
Use `approve` when you reviewed a teammate's PR, recommend approving it, and the only move left is
your user's Approve on GitHub; name the PR under `Needs`. It sorts and reminds like `merge`.
Use `running` when nothing waits on your user but you are minding a pipeline run or another long
process; name it and its tmux `session:window` under `Running`, whose first line its card shows.

New briefs include a readable slug and WordyBin suffix, such as
`Lemon-ID: mc-tars-no-mops-leases.SkullHen`, generated from the brief filename
and two random bytes. The slug omits the leading date and is trimmed to about
40 characters at a hyphen boundary.
Attaching or messaging an existing brief adds the line if it is missing. The ID names its
message inbox and stays with the brief when its filename or attached channel changes.
`brief id` also backfills an existing attached brief.
`brief id --reroll` (or `--set <WordyBin>`) replaces the WordyBin and moves the inbox, parent
links, and brief line to the new ID; the old ID stays an alias, so messages sent to it still
arrive. It prints `old -> new`; with `--json`, `lemon_id`, `old_lemon_id`, `signing_name`, and
`old_signing_name`. Pass the old signing name to doc waiters as `--legacy`, and rearm your inbox
waiter, which exits. See `docs/messages.md`.
Older hexadecimal and hand-made IDs remain valid and keep their inbox folders.
An ID's shape is not validated; only folder safety is checked. It must be
non-empty, at most 255 UTF-8 bytes, and have no slash, backslash, control
character, or leading dot.

Make routine changes to `## Now` with `brief bullet` and `brief pr` rather than by editing the
file. They keep its `###` sub-headings in the order the rules give (Needs, Running, Waiting on,
Next, PRs, Done), with a blank line around each, and remove a heading or PR table left empty.
`## Questions` and every other section stay as written. `bullet add` takes the heading
(`Needs <who>` keeps who it names); `set` and `rm` name a bullet by the start of its text, case
ignored, and fail unless exactly one bullet in `## Now` matches. Bare URLs and vault paths in a
bullet become short links, as in the brief view. `pr add` takes the PR's URL, or its number when
`[brief] pr_url` is set (`docs/config.md`); adding a PR again updates its row, keeping its review
link unless `--review` gives a new one. `--review` takes a URL or a `.md` path under a
`[brief] vaults` root, which becomes an `obsidian://` link.

Keep `## Waiters` current with `brief waiter`: add a waiter's command when you start it, `set`
it when you rearm it differently, and `rm` it when you stop it. Each waiter is a bullet holding
its command in backticks. A missing `## Waiters` is added as the last section, and notes in it
that aren't bullets stay as written. `set` and `rm` name a waiter by any part of its command,
case ignored, and fail unless exactly one matches, listing the ones that do. `set --head <sha>`
keeps the command and changes its `--head` (filling a `<head SHA>` placeholder, or adding the
flag), so rearming `watch pr` on a new push is one short command. Adding a command already
listed changes nothing.

`brief check` (`--self`, another target, a file, or `--all` for every brief attached to a session
that isn't archived or waiting for one) reports what is wrong with a brief:
- more or fewer than one `# ` title, or a `## ` section that appears twice;
- a missing, repeated, or unknown `Status:` word;
- a malformed `Lemon-ID` line, or one that differs from the ID the database records for the file;
- `## Now` sub-headings out of order, repeated, empty, or without a blank line above and below;
- a `### PRs` table that is not `| Work | PR | Review |` rows with a pull-request link in each,
  or that has no rows;
- a `## Waiters` section that is not last;
- no `Parent:` line, when the database records a parent for the brief;
- with `--all`, an attached brief whose file is gone.

It exits 1 when it finds anything, and `--json` lists the problems. Every edit verb (`now`,
`status`, `bullet`, `pr`, `waiter`) runs it on the result and refuses the edit if it finds
anything, listing what. A brief that already fails takes only an edit that fixes it: `brief status` fixes a bad
`Status:` and any `## Now` edit puts the sub-headings in order, but a misplaced `## Waiters` or a
wrong `Lemon-ID` needs a hand edit first. `brief now` lays out the section it is given the same
way the other verbs do. The verbs never drop a `Parent:` line, and refuse an edit that
would, but they still edit a brief that has already lost one. A `Parent:` or `Area:` line given to
`brief now` replaces the brief's line for that field, and a field it leaves out stays as it was. A Claude lemon's Stop hook
runs it too, and blocks the turn's end until the brief passes. **After editing a brief by hand,
run `lemonaid brief check --self`**: nothing else checks a Codex lemon's hand edits.

A sandboxed lemon (Codex writes only inside its workspace) keeps its brief current with these
verbs; any other lemon may do the same or edit the file directly.

A brief's real path must be inside the active brief folder: `attach`, `place open --brief`, and the
edit verbs refuse anything else, including a symlink that points out of it, since they write for lemons
whose sandbox would otherwise stop them. The edit verbs change one section and replace the file
whole; if it is saved in between (in an editor, say), they re-apply the change to the newer text.

`brief list --json` is how a tool maps a brief file back to its session: one entry per brief, with
`path`, `channel`, `id` (the inbox row), `name`, `archived`, `tmux_session`, `tmux_window`, and
`pending` (true while it waits for a lemon to start; `channel` is then null).

```bash
lemonaid brief show                  # the briefs of every lemon in the calling window, as markdown
lemonaid brief show --self           # only your own attached brief, not the other lemons' in your window
lemonaid brief show <session>[:<window>]  # another session's; the window picks one lemon in it
lemonaid brief show --file <path>    # a brief file, without asking tmux
lemonaid brief show --dir <path>     # a directory's .z/, without asking tmux
lemonaid brief show --dir <path> --place <dir>  # also .z/ above <path>, up to <dir>
lemonaid brief show <session> --popup  # in a tmux popup over your own client
lemonaid brief show --no-questions   # hide matched Questions entries for a compact text view
```

Output for a recorded session starts with its identity and the brief's `Status:` line, then its `Needs` part as a
blockquote, then the rest of `## Now` with `Done` last, then the rest of the brief below a rule; the
directory, branch, brief path and age come last. `--file` resolves an attached session from the inbox, while `--dir` has no session header. The briefs attached to the session's lemons come first; when the session holds several lemons
and no window picks one, each attached brief names its lemon above its Status and Now. `b` in the TUI
opens the same popup for the selected session.

A `## Questions` entry is a `###` heading named with the label of the `Needs` bullet it
explains: the bullet's text up to its first colon, or the whole bullet, ignoring bold and case.
`brief show` displays matched entries under their Needs bullets by default; `--questions` remains
accepted, and `--no-questions` hides matched entries in text output. A Questions heading with no
matching Needs bullet is flagged in both text and popup views, and `brief check` reports it.
An existing mismatch does not prevent an unrelated `brief status`, `bullet`, `pr`, or `waiter`
edit; an edit that creates a new mismatch is refused.
When the person answers from the
brief view, or asks for more detail, the lemon gets a message in its inbox:
`Answer to <label>: <text>`, or `More detail needed on <label>: rewrite that entry in
## Questions`, from the person's `$USER`. While your Status is `blocked`, `alert`, `merge` or
`approve`, an answer ends with a line naming the `Needs` labels it leaves, as a reminder to update
Status if the answer changes it.

While your Status is one of those four, lemonaid reminds you what it waits on once a turn: a
Codex lemon at the end of each message queued into its thread, and a Claude lemon on the first
tool call of each turn, when the `status-note` hook is installed. Update Status if the turn
answers or changes one of them; otherwise ignore it.

On your first turn of each day (from 06:00 local, unless configured) lemonaid adds one line with the time, weekday and date
("It's 9:14am Thursday, 2026-10-01."). Trust it over the date your session started with.

A session with no attached brief falls back to `.z/`, for sessions started before briefs moved out of
it. It looks in the working directory of each lemon the inbox has in that session, then the session's
own directory, and uses the first that has a brief. When that directory has several, the one named
after the lemon's `LEMON_NAME`, its backend (`brief-codex.md`), or the tmux session is shown; failing
that, all of them, newest first, each with only its Status and Now. The backend counts only when the
session holds one lemon. With no brief, `.z/state.md` stands in.

The session's directory is the place, and the `.z/` search never leaves it. A lemon working in a
subdirectory finds the place's `.z/`, but a `.z/` above the place, or in a lemon's working directory
outside it, belongs to other work, so a place without a `.z/` of its own has no brief.

**Keep `Status:` and `## Now` current if you work from a brief.** They are what a person reads without
switching to your session:

```markdown
Status: working

## Now
- Done: <what is finished, with PR numbers>
- Next: <what you are doing now>
- Needs: <a decision or action from a person, or "nothing">
- Waiting on: <who or what has the next move, or "nothing">
- Running: <the long process you are minding, and its tmux session:window>
```

Each part can instead be a sub-heading (`### Needs`, `### Running`, `### Waiting on`, `### Next`, `### Done`)
with anything under it. `Needs` may name who it needs (`Needs you`); readers show it first
whatever order you write, and show the live state of any `PR #N` or pull-request URL you mention when the user has configured `[brief] pr_state`.

## Lemon-to-lemon messages

With a brief attached to the recipient's channel, `lemonaid tell <lemon-id-or-channel-or-brief>
"<message>"` writes a Markdown file to its inbox. Set `LEMONAID_CHANNEL` to
your own channel to identify the sender and to use `lemonaid inbox next --self`
or `lemonaid inbox watch --self`. An exported Claude session ID or Codex thread
ID also identifies self without tmux. Otherwise, lemonaid resolves the current
tmux pane and refuses ambiguous matches. Pass `--channel <your-channel>` to
override receive identity. Both print one message and move it to `done/`;
watch waits until one exists, or use `--timeout <seconds>` to bound the wait.
A Codex lemon needs no waiter: lemonaid's delivery service queues each message
into your thread with `codex queue`, and starts itself when a message is sent.
A Claude lemon with a brief keeps `lemonaid inbox watch --self` running as a
background task; if the `waiter-check` Stop hook is installed, it refuses to
let your turn end until that watch is running. Start it with
`run_in_background` and `timeout: 2147483647`: since Claude Code 2.1.285 a
background task otherwise stops after 30 minutes. That timeout needs
`BASH_MAX_TIMEOUT_MS` raised in the user's settings (see
[Claude setup](claude.md#2-keep-background-waiters-running)). If the
harness stops the watch anyway, rearm it, even though its notice says not to
restart a task that already had the maximum timeout. The same goes for
`watch doc` and `watch pr` waiters.

When Codex uses the automatic approval reviewer, set up the `lemonaid brief`,
`lemonaid tell`, `lemonaid inbox watch`, and `lemonaid inbox next` allow rules
described in [Codex setup](codex.md#2-allow-brief-and-message-commands-under-the-automatic-approval-reviewer).

## Watching a document for comments

`lemonaid watch doc --wait <doc> --me <your name> --once` blocks until a Relay Comment
thread in `<doc>` is waiting on you, prints one line, and exits. Run it as a background task
(Claude), or pass a bare `--codex-thread` to have the event queued into your
Codex thread instead. `--status <doc> --me <name>` says whether a waiter is already running;
a second one for the same doc and name refuses to start (exit 3). OpenClaw sessions use
`lemonaid watch openclaw start <doc> --session-key <key> --me <name>`. Details: [watch.md](watch.md).

Your own edits to the doc's body don't wake your own waiter, as long as they're recorded.
Claude Code records `Edit` and `Write` calls itself when `lemonaid claude hooks --own-edits` is
installed. For an edit made any other way (Codex, or a Claude edit through Bash), run
`lemonaid watch doc --editing <doc>` just before it and `lemonaid watch doc --mine <doc>` right
after. Codex does all three in one shell call:

```sh
lemonaid watch doc --editing <doc> && apply_patch <<'PATCH' && lemonaid watch doc --mine <doc>
*** Begin Patch
*** Update File: <doc>
...
*** End Patch
PATCH
```

Edits by anyone else, another lemon's included, still wake you. Details: [watch.md](watch.md#ignoring-the-lemons-own-edits).

`lemonaid watch pr --wait <n> --head <sha you handled> --comments --me "<signature>" --once` does
the same for a GitHub PR: a push, merge or close, draft or review-decision change, new
comment from someone else, conflict with the base, or failed CI (the last three only with `--comments`).
Sign each GitHub comment right after the marker, `🍋 Author (MotorHoe): ...`, and pass that
signature as `--me` (`--legacy` for older ones): only comments signed that way are skipped as yours. Rearm with `--head` set to the head you just handled.

`lemonaid watch file --wait <path> [--wait <path> ...] --me <name> --once` waits for a file
to change, or for a file directly in a directory to be added, removed, or rewritten.

## Installing the watch skills

`lemonaid skills install` installs the `watch-doc` and `watch-pr` skills for Claude Code
and Codex, which describe these waiters step by step. It never replaces a skill entry it
didn't create; `--print <name>` gives the text instead. Run it after installing or
upgrading lemonaid; `lma` also re-renders installed skills from the new packaged text when
it starts after an upgrade. Details, including the `~/.lemons/skills/<name>/overlay.md` a
user adds their conventions in:
[skills.md](skills.md).
