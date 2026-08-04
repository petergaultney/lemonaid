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

### Add a notification

```bash
lemonaid inbox add "channel-name" "Title" -m "Optional message" --metadata '{"key": "value"}'
```

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
| `switch_source` | string? | Switch-source: `tmux`, `wezterm`, or `null` (determines which switch-handler can navigate back) |

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

### Getting a session for a place

```bash
lemonaid place open <key> --json           # acquire if needed, then open a session
lemonaid place open <key> --detach --json  # ... without stealing the terminal
```

Idempotent: the directory is acquired only if it doesn't exist, its session is switched to
only if there isn't one, and neither case is an error. Always safe to run without checking
first, so don't probe for existence beforehand. `--json` returns
`{"key", "dir", "root", "error"}`.

**Use `--detach` whenever you are not acting on a direct request to go somewhere.** Without
it, each call switches the user's terminal — so opening three places in a row leaves them
somewhere they didn't ask to be, twice. Detached, the session is created and left alone.

The tmux session is named after the key (with `.` and `:` replaced, since tmux forbids them),
so `tmux send-keys -t <key>` and similar work afterward. `place list --json` reports the
actual name.

Acquiring a directory can take minutes — it may install dependencies. Don't set a short
timeout and don't retry on a timeout; a second call would just wait on the same work.

### A session where there is no place

Run from a directory no configured root manages the names of, there is no key to resolve,
so the name is simply a session opened in the current directory. Nothing is acquired, and
the JSON reports `"root": null`.

```bash
cd ~/somewhere-unmanaged && lemonaid place open notes --detach --json
# {"key": "notes", "dir": "/home/me/somewhere-unmanaged", "root": null, "error": null}
```

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

### Tearing one down

```bash
lemonaid place toss <key> --json
```

**The unit is a tmux session, not a directory.** A key names the session sitting in that
place, and teardown covers *everything that session occupies* — which may be more than the
one place you named. The response tells you what actually happened:

```json
{"session": "stacked", "released": ["feat/base", "feat/on-top"], "error": null}
```

If it matters which places a session owns, check `place list --json` first and look at the
`session` field.

**Always pass the key.** Named, it works from anywhere, which is what you want — you have no
reliable idea which tmux session your shell is attached to. The unnamed form acts on the
session you happen to be attached to.

**`--json` implies `--yes`**, so it does not prompt. It still refuses when the root's
`inspect` command reports uncommitted or unpushed work; `--force` overrides that. **Do not
pass `--force` on a user's behalf without being asked to** — it is the difference between
tearing down unattended and discarding work.

Two kinds of protection, and `--force` overrides neither:

- A root's `protected` keys (`main` and `master` by default) are never released and never
  count as owned, so a session sitting in one simply reports no places.
- `protected_sessions` under `[places]` refuses teardown of that session entirely. Naming a
  place it occupies is not a way around it.

A session with no managed places is fine to toss — it just kills the session.

Teardown finishes after the command returns — releasing a large directory is slow, so it
runs detached. Its output goes to `~/.local/state/lemonaid/reap.log`.
