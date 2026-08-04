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

### The protocol is lines

`list` emits one absolute path per line (optionally `path<TAB>label`); `inspect` emits one
short line, or nothing. That's it — no JSON schema to satisfy, which is why the `list` above
is plain `git` rather than anything worktree-tool-specific.

`inspect` decides for itself what's worth saying. It should stay quiet when there's nothing
to report, so that `place list` over a large repo highlights only what needs attention.

### Why `create` and `path_of` are separate

A tool that creates a directory usually reports it by changing *its caller's* working
directory, which a subprocess can't observe. So `create` runs, then `path_of` is asked where
the thing went.

## Commands

```bash
lemonaid place open <key>      # get a session for this, whatever it takes
lemonaid place list            # every directory each root reports
lemonaid place toss [<key>]    # kill a session and release the places it occupies
lemonaid place hooks           # show what's configured
```

`place open` is idempotent, in the same spirit as `wt co`: it acquires the directory only if
it's missing, switches to its session only if there isn't one, and neither case is an error.
You never have to know which situation you're in. (`place new` is a hidden alias, since
naming it after creation misdescribes the common case.)

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

## Teardown

You can already delete a worktree and you can already kill a tmux session. What you can't do
is remember which worktrees a session started, or which session is hosting a worktree — and
that bookkeeping is the whole reason cleanup gets deferred until you've lost the context to do
it well.

So `toss` works on a session and everything it occupies:

```bash
lemonaid place toss          # the session you're attached to
lemonaid place toss <key>    # the session sitting in that place
```

Both forms resolve to the same thing. A key is a way of *naming* a session, not a second mode
— which is what stops `toss base` from killing a session and stranding the other place it
owned.

The set is shown before anything happens:

```
$ lp toss
session 'stacked'
  feat/base
  feat/on-top - 2 unpushed
kill it and release 2 places? [y/N]
```

That prompt is where your in-the-moment context gets used. A session with nothing managed
under it just asks `kill it?` — sessions without a worktree are ordinary, not a special case.

### Ownership is derived, not recorded

A session owns the managed places its panes sit in, worked out from tmux when you ask:

```bash
tmux list-panes -a -F '#{session_name}|#{pane_current_path}'
```

Nothing is written down when a place is opened, so nothing can drift. A worktree you made by
hand, one `place open` made, and one an agent made all resolve identically afterward — which
matters because the agent-created ones are exactly the ones you'd otherwise never find.

tmux keeps reporting a pane's original path after the directory is deleted, so a session that
outlived its worktree still resolves and can still be closed.

### Protection and flags

Two kinds, guarding different things.

**Protected places** — `main` and `master` by default — are never released, and never count as
owned. Everyone passes through the trunk worktree, and a line in every confirmation that can
never be acted on is one you learn to skip past, which is how a real entry gets missed. So a
session parked in `main` simply owns nothing. Set `protected = [...]` on a root to change it.

**Protected sessions** are refused outright:

```toml
[places]
protected_sessions = ["main", "lemonaid"]
```

A long-lived catchall session isn't tied to one piece of work, so tossing it loses windows
rather than finishing something. Configured globally rather than per root, since a session's
name isn't repo-scoped and the one you want to guard may not sit in a managed directory at all.

`--force` overrides neither.

- `--yes` skips the confirmation. `--json` implies it.
- `--force` proceeds despite `inspect` reporting work.

They're separate so an agent can tear down unattended without also being able to discard
commits you haven't pushed.

### Order of operations

1. Ask `inspect` about each place being released; refuse if it reports anything (`--force`
   overrides).
2. Show the set and confirm (`--yes` skips).
3. Switch you to another session — wherever you came from, else one that wants attention in
   the inbox, else the most recently active.
4. Kill the session and run `destroy` for each place, in a detached process.

Step 3 exists because you're usually inside what's being destroyed; if there's nowhere to
switch to, `toss` refuses rather than stranding your client. Step 4 is detached because
releasing a large directory takes a while. Output goes to `~/.local/state/lemonaid/reap.log`.

The session is killed *before* any directory is released: your shell's working directory is
inside one of them, and a process still holding a file there can make the removal fail. A
place whose directory is already gone is skipped rather than treated as a failure.

## Sessions that outlive their tmux session

Selecting a session in the inbox whose pane is gone recreates it in the same directory. Your
archive already records where work was happening, so a dead session and a live one answer to
the same key — you don't have to know which you're looking at.
