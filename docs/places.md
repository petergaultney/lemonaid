# Places

A **place** is a directory you work in. If you go through a lot of them in a day — git
worktrees, per-branch checkouts, scratch clones — the friction isn't the work, it's the
setup and teardown around it.

Setting one up is two commands (make the directory, then make a session in it), and one of
them blocks while dependencies install. Tearing one down is worse: killing the tmux session
leaves the directory, removing the directory leaves the session, and nothing knows the two
went together.

Places make both one command.

## lemonaid doesn't know what a worktree is

It knows about directories and terminals. Anything that creates or removes directories is a
shell command you declare per root:

```toml
[[places.roots]]
path = "~/work/somerepo"
list = "git -C .bare worktree list --porcelain | grep '^worktree ' | sed 's/^worktree //' | grep -v '/\\.bare$'"
path_of = "wt path {key}"
create = "wt co {key}"
destroy = "wt rm -f {key}"
inspect = "wt status {dir}"

[[places.roots]]
path = "~/play/somethingelse"
# a plain clone - nothing to list, create, or destroy
```

Every command is optional; unset means that capability no-ops for that root. So a normal
clone coexists with a worktree repo, and nothing needs to detect which is which.

`{key}` is whatever your tool names directories by — a branch name, above. lemonaid passes
it through without interpreting it. `{dir}` is an absolute path.

The commands run through a shell, so pipelines work. They come from your own config file,
which is the same trust level as your shell rc.

A root also names the project its places belong to, which brief cards show on their first
line. That's the root's directory name unless you set `name`, which helps when the
directory is named for its layout:

```toml
[[places.roots]]
path = "~/play/lemonaid-wt"
name = "lemonaid"
```

A session outside every root is named for its own directory.

<img width="600" alt="A brief card in the sidebar, led by its project and area, kitchen: apps/breadbox" src="images/brief-project-area.png" />

### The protocol is lines

`list` emits one absolute path per line (optionally `path<TAB>label`); `inspect` emits one
short line, or nothing. That's it — no JSON schema to satisfy, which is why the `list` above
is plain `git` rather than anything worktree-tool-specific.

`inspect` decides for itself what's worth saying. It should stay quiet when there's nothing
to report, so that `place list` over a large repo highlights only what needs attention.

### PR numbers in the inbox

Inbox rows show `#number` before the session name in both layouts. The row's working directory selects its innermost configured root, and its `git_branch` is looked up in that root's open-PR map first.

When branch lookup finds no number, an attached brief's `### PRs` table supplies the fallback if it has exactly one valid row. Empty, invalid, or multi-row tables supply no number. Children and their roles do not affect the result.

Set `open_prs` to a shell command that prints one `<branch> <number> [url]` line per open PR:

```toml
[[places.roots]]
path = "~/play/myrepo"
open_prs = '''gh pr list --state open --limit 1000 --json headRefName,number,url --jq '.[] | "\(.headRefName) \(.number) \(.url)"''''
```

The optional third field is an HTTP(S) PR URL. A number with a URL is a terminal hyperlink: use your terminal’s modifier-click gesture (Ctrl-click or Cmd-click). Brief-table fallbacks retain their link URL. Two-field hooks still show a number without a link; conflicting URLs for the same number leave it unlinked. See [tmux hyperlinks](tmux.md#pr-hyperlinks) for tmux setup.

The command runs in the root directory, off the UI thread, at most once every three minutes per root. Failed commands clear the map, malformed lines are ignored, and a branch with several different PR numbers has no map entry and uses the same brief-table fallback. Reviewers sharing their author's branch show the same number. The hook is optional and can use any forge or tool that emits these lines.

### Why `create` and `path_of` are separate

A tool that creates a directory usually reports it by changing *its caller's* working
directory, which a subprocess can't observe. So `create` runs, then `path_of` is asked where
the thing went.

## Commands

```bash
lemonaid place open <key>      # get a session for this, whatever it takes
lemonaid place acquire <key>   # just the directory, no session
lemonaid place list            # every directory each root reports
lemonaid place toss [<key>]    # close a workspace, with optional directory cleanup
lemonaid place hooks           # show what's configured
```

`place open` is idempotent, in the same spirit as `wt co`: it acquires the directory only if
it's missing, switches to its session only if there isn't one, and neither case is an error.
You never have to know which situation you're in. (`place new` is a hidden alias, since
naming it after creation misdescribes the common case.)

Choose a configured lemon with `--harness NAME`, such as `claude` or `codex`. The
name selects the matching entry under `[tmux-session.templates]`; without it,
`default` is used. An
initial prompt can be passed directly to that template's harness command:

```bash
lemonaid place open feat/thing --harness codex --prompt 'read .z/brief.md and do what it says'
```

`--brief <file>` attaches a brief (a path, or a name in `~/.lemons/brief/`) to the
first lemon that starts in the session's harness window, so the prompt can just
say to read it. See `lemonaid for-lemons` for the `brief` commands. `--parent self` (or a Lemon-ID) also records the caller as that brief's lemon's parent; see [parent links](lineage.md).

The prompt is set as `LEMONAID_PROMPT` in the environment of the window's shell, and the
command in `harness_window` (or `resume_window` when `harness_window` is unset) gets
`"$LEMONAID_PROMPT"` appended. A POSIX shell, fish, and xonsh all read that as one
argument, whatever the prompt contains, so lemonaid needn't know your shell's quoting.
A one-command line runs as `env -u LEMONAID_PROMPT <command> "$LEMONAID_PROMPT"`, so the
lemon and its tool calls don't inherit the variable. The window's shell keeps it, since
unsetting a variable is spelled differently in each shell, and so does a compound line's
harness. Nothing but the launch line reads it. These
options only affect creation; if the place already has a session, `open` keeps
its idempotent behavior and switches to that session without injecting a new
prompt. See [the configuration reference](config.md#tmux-sessiontemplates).

`place acquire` is the same acquisition without the session, printing the directory — so
`cd $(lemonaid place acquire feat/thing)` works. It exists for callers that aren't tmux
clients: an agent has its own session and will never attach to one, so `place open` would
leave an unused session behind for every directory it made. Since nothing is recorded either
way, the two produce places that are indistinguishable afterward.

Outside every root that has a key vocabulary, there's no key to resolve, so `place open
<name>` is just a named session in the current directory — the same thing `tmux new -s` gets
you, by way of your session template. Nothing is acquired.

That's decided by where you are, not by whether a lookup succeeded. Inside a root with a
vocabulary the name is always a key, so a mistyped one acquires a directory rather than
silently becoming an empty session. A root with no `list` and no `path_of` has no vocabulary
to speak of — it's there so `place list` reports the directory — so being inside one is the
same as being outside every root.

For these sessions the name is the identity, not the directory, so two differently-named
sessions in one directory are fine. `place list` won't show them; they're sessions, not
places.

Add `--detach` to skip switching to it, and `--json` to any of these for machine-readable
output. `list --json` includes each place's key and its live tmux session name (empty when
nothing is running there), which is what an agent needs to act on a listed place. See
[for-lemons.md](for-lemons.md) for the full programmatic surface.

A root's `list` hook may occasionally report a valid directory outside the
configured root, for example a temporary git worktree. Lemonaid ignores and
logs that entry because it cannot derive a key in the root's namespace; other
places continue to list normally.

## Teardown

`toss` retires a one-off tmux workspace. It closes the whole selected session,
then releases associated directories through the roots' `destroy` hooks. Each
hook runs in its own root, and confirmation labels include that root so identical
keys remain distinct. Those
hooks can remove worktrees and their branches; lemonaid itself knows directories
and terminals. A session without a managed directory is an ordinary target.

```bash
lemonaid place toss                 # current tmux workspace, with confirmation
lemonaid place toss <session>       # exact workspace name, from anywhere
lemonaid place toss <session> --yes # unattended callers must name it
```

A named tmux session wins over a same-named managed directory. Inside tmux,
interactive bare `toss` selects the current session regardless of the caller's
working directory. `--yes` and `--json` require an explicit session name.
The confirmation defaults to no and shows all closing windows, released
directories, and directories being kept.

```
$ lp toss relay-notifications
workspace 'relay-notifications'
  session 'relay-notifications' closes (2 windows)
close this workspace? [y/N]
```

If no session matches a supplied name, the existing directory-key cleanup is
available. Outside tmux, bare `toss` uses the managed directory at the current
working directory. Directory targeting can close windows in shared sessions;
the confirmation identifies them before anything happens.

### Single-purpose and hybrid workspaces

Toss refuses a hybrid workspace: one whose live lemons occupy unrelated places.
The error says that the workspace is not a managed place, and no terminals or
directories close. An author and reviewer sharing a place count as one purpose;
working in different subdirectories of that place does not make it hybrid.
When discovery cannot establish a shared place, distinct lemon paths refuse
teardown even if one is beneath the other.
Scratch inbox panes and follow placeholders do not count. Classification uses
live harness processes and pane paths, rather than stale inbox rows, and is
checked again after confirmation. `--force` does not override this refusal.

With one lemon, or several lemons sharing a place, toss closes the workspace
and performs its optional directory cleanup. With no identifiable lemons, toss
still closes the workspace, but releases a directory only when all its work
panes consistently occupy the same managed place. Otherwise the directories stay.
A failed process inspection refuses teardown rather than treating it as an
empty workspace.

### Optional directory cleanup

Associated directories come from the session's pane paths and its name, matched
to directories reported by configured roots. A session named for a directory
can clean it up even after its shells change directories. Nested directories
match the most specific managed place.

A directory stays when it is protected, used by another workspace, contains
another managed directory, or has no `destroy` hook. If any pane's directory
is unknown, directory cleanup is skipped. Failed directory discovery or lookup
also skips cleanup while allowing the named workspace to close. A failed lookup
in a root with neither a matching listed key nor a pane in the workspace does
not block cleanup in another root. Reasons appear in the confirmation, in
unattended text output, and in the JSON `kept` list. No other workspace closes to make a directory releasable.

```
$ lp toss job
workspace 'job'
  session 'job' closes (3 windows)
  directory 'feat/work' stays (used by another workspace)
close this workspace? [y/N]
```

A successful lookup may report a directory that is already gone. Its workspace
can still close, and no destroy hook runs for the missing directory.

### Protection and flags

Protect long-lived workspaces explicitly by their exact tmux session names:

```toml
[places]
protected_sessions = ["hq", "ds-monorepo/main"]
```

Protected sessions are never closed, including through directory-key cleanup.
The hybrid-workspace guard also applies without config. Explicit protection covers
long-lived single-purpose sessions, including HQ when it has only one lemon.
Root-level `protected = [...]` guards directories (`main` and `master` by default),
so a job visiting a protected directory can close while the directory stays.

An editable lemonaid install's source directory cannot be released. Unfinished
work reported by an `inspect` hook still refuses cleanup unless `--force` is
supplied. `--force` does not override protection or shared-directory retention.
`--yes` skips confirmation; `--json` implies it. JSON's `session` names the closed
workspace and `released` lists its optional directory cleanup.

The interactive confirmation names affected lemons whose attached brief says
`merge`, `approve`, `blocked`, or `alert`, with each name and status in the
inbox's status text color. This includes Codex daemon rows in directories being
released. Pressing Enter declines the toss; type `y` or `yes` to confirm.
`--yes` and `--json` still skip the confirmation.

### Which inbox rows are archived

`toss` closes terminals and releases directories. The inbox watcher archives terminal
rows after their panes or harness processes exit. A lemon in a surviving pane keeps
its row and pin even if its last recorded cwd is inside the released place. The
watcher must be running for terminal rows to leave the inbox.

After teardown starts successfully, toss records which terminal rows it intended to
close. The watcher honors this evidence once their panes or harnesses exit, even if
an attached brief is `merge`, `approve`, `blocked`, or `alert`. This overrides brief
protection only for the recorded terminal identity; moving or resuming the lemon in
another terminal leaves the usual protection in place. A failed teardown records
no evidence.

Toss directly archives only Codex rows without their own recorded terminal identity.
Shared app-server hooks have no tty, and older hooks could record the daemon's tty.
These rows use cwd membership: toss archives them only when their recorded cwd is
inside an existing place directory being released by `destroy`. Codex CLI rows with
TTY, pane identity, and session order are left to the watcher like other terminal rows.

The Codex fallback set is captured before directories disappear and archived only
after teardown starts successfully. A place with no `destroy` hook, or whose directory
is already gone, does not archive rows by cwd. Closing a bare session leaves inbox
cleanup to the watcher.

### Order of operations

1. Work out the place, which windows sit in it, and whether its session is dedicated to it;
   select the workspace and optional directory cleanup, refusing protected sessions.
2. Ask `inspect` about the place; refuse if it reports anything (`--force` overrides).
3. Show the set and confirm (`--yes` skips).
4. Switch every client attached to a closing session to another one — that client's last
   session, else wherever you came from, else one that wants attention in the inbox, else the
   most recently active. A client looking at a window that closes on its own is moved to
   another window of the same session.
5. Make the plan again from a fresh look at tmux and compare. The confirmation prompt can sit
   for as long as you take, and any difference - a pane that moved, a window split or opened
   in the place, a session that gained a window - stops the whole toss: nothing closes and
   nothing is released.
6. Close the windows that close on their own, except the one this command runs in.
7. Kill the session, close that last window, and run `destroy` for the place, in a detached
   process.

Step 4 covers every client, not just the caller's: an agent tossing a place by key usually
runs in some other session while you watch the one going away. If any client has nowhere to
switch to, or tmux can't list the session's clients, `toss` refuses rather than risk
detaching one. Step 7 is detached because releasing a large directory takes a while, and
because closing the caller's own window would end the command before it could release
anything. Output goes to `~/.local/state/lemonaid/reap.log`.

The session and windows are closed *before* the directory is released: your shell's working
directory is inside it, and a process still holding a file there can make the removal fail. A
place whose directory is already gone is skipped rather than treated as a failure.

## Resuming detached tmux rows

Live inbox rows keep their normal activation behavior. A detached tmux row can be resumed with
`R`: lemonaid first checks the recorded tmux session identity, then falls back to the saved
directory only when it identifies exactly one existing session. It opens a new window in that
session and runs the backend's `resume_command`. If no unique safe destination is available,
lemonaid shows a copyable command so you can paste it into the session you choose. It does not
start another tmux session. A row without a backend resume command is marked `resume unavailable`.
