# Audit log: who did what

Lemonaid records each action that moves, removes or rewrites state a person or another lemon owns, with the actor worked out automatically. Read it back with:

```bash
lemonaid audit                         # the last 20 actions, oldest first
lemonaid audit --by BlessBar -n 0      # everything an actor matching "BlessBar" did
lemonaid audit --thing LunarLap        # everything done to a brief, lemon, channel or place
lemonaid audit --json                  # the same, as a JSON list
```

`--by` and `--thing` match case-insensitive substrings. `--thing` searches the thing acted on, its place key, tmux session, directory, source and destination paths, and channel. Place opens and tosses are included; `lemonaid place log` still shows only those.

## What is recorded

| Action | When | `why` |
|---|---|---|
| `brief-archive` | A brief and its mailbox move to the attic, from `brief archive`, the idle sweep or a place toss. | `by hand`, `idle sweep: unused N+ days`, `place toss` |
| `brief-revive` | An archived brief comes back, from `brief revive` or a message that resumes an archived lemon. | `by hand`, `resume of an archived lemon` |
| `brief-edit` | A brief verb (`status`, `now`, `bullet`, `section`, `pr`, `doc`, `lemon`, `watching`, `hide`) or the inbox changes a brief that isn't the editor's own. | (the command line is in `argv`) |
| `lemon-parent` | `lemon parent --set` or `--clear`. | `set to <Lemon-ID>`, `cleared` |
| `lemon-restart` | `lemon restart` stops and resumes a lemon. | `forced` with `--force` |
| `inbox-archive` | A card leaves the inbox: `inbox archive`, the inbox's archive key, a place toss, or the inbox watcher's auto-archive of an ended session. | the command, or the watcher's reason and evidence |
| `inbox-unarchive` | `inbox unarchive`. | |
| `inbox-purge` | `inbox purge` deletes old rows. | the age cutoff |
| `open`, `toss` | `place open` and `place toss`; see [places](places.md#audit-log). | the refusal or error |

Tasks are not in this log: each task keeps its own event history with the actor (`lemonaid task show`).

## Who did it

Every event carries `who`, `via` (the evidence used), `channel`, `pid`, `parent` (the parent process's name) and `tty`. The first source that names someone wins:

1. `code`: lemonaid names the actor itself for its own jobs: `idle sweep` (through `LEMONAID_ACTOR`, set when the daily sweep starts) and `inbox watcher`.
2. `env`: the harness's session variables (`LEMONAID_CHANNEL`, `CLAUDE_CODE_SESSION_ID`, `CODEX_THREAD_ID`) name a channel. `who` is that channel's Brief-ID, or the channel when no brief is attached.
3. `tmux`: the inbox records a lemon in the tmux pane the command runs in, and a harness (`claude`, `codex`) is among the command's parent processes. A person typing in a suspended lemon's pane is named by step 4 instead.
4. `tty`: a terminal on stdin and none of the above: a person, named by their login.
5. `ppid`: nothing else; the parent process's name, or `unknown`.

The lookup uses a read-only database connection with a short timeout, so recording never registers a brief or waits behind a writer. A process inherits its parent's environment, so a lemonaid job started from a lemon's command must set `LEMONAID_ACTOR` to be named as itself.

## Files

Events go to `~/.local/state/lemonaid/logs/actions.log` (place events to `places.log` beside it), one JSON object per line; `$LEMONAID_STATE_DIR` moves the state directory. Each file rotates to `<name>.1` past about 1 MB, replacing the older rotation; writers take `<name>.lock` so two can't both rotate. A failed write is logged and the action goes ahead. `argv` holds the command line, cut to 300 characters.
