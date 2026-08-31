# TUI Keybindings

All keybindings in the `lma` TUI are configurable via `~/.config/lemonaid/config.toml`.

## Default Keybindings

| Key | Action |
|-----|--------|
| `Enter` | Open notification (switches to that session) |
| `1`-`9`, `0` | Switch to that row of the list, counting from the top |
| `u` | Jump directly to earliest unread session |
| `m` | Mark as read |
| `M` | Mark as unread again |
| `a` | Archive (remove from list) |
| `s` | Snooze session (pick a duration) |
| `S` | Toggle snoozed view |
| `z` | Undo the last inbox change |
| `r` | Rename session (clear to revert to auto-name) |
| `H` | Save scratch pane size (follow mode, only when it has drifted) |
| `f` | Move the scratch pane between top and left |
| `h` | Toggle history view |
| `g` | Refresh |
| `?` | Toggle the key hints (see below) |
| `q` / `Escape` | Quit |
| `↑` / `↓` | Navigate list |

The key hints occupy the bottom row for the first 10 seconds, then hand it back to
the unread/read counts. `?` brings them up again and cancels that timeout, so they
stay until you press `?` a second time. `?` is not configurable.

### History mode

| Key | Action |
|-----|--------|
| `Enter` | Resume selected session (replaces current terminal) |
| `c` | Copy resume command to clipboard |
| `T` | Spawn a tmux session around the selected session |
| `/` | Filter by name, cwd, branch |
| `h` | Exit history |

### Snoozed mode

| Key | Action |
|-----|--------|
| `Enter` | Wake the selected session now (returns it to the inbox) |
| `S` / `q` | Back to the inbox |

## Snooze

`s` holds a session out of the inbox until a time you pick: 15 minutes, 1 hour,
4 hours, tomorrow morning (9am), or a custom duration (`45m`, `2h`, `3d` — a bare
number means minutes).

When the timer expires the session returns with the status it had when you
snoozed it: one that was demanding attention comes back unread, one that was
merely idle comes back read. Nothing is ever hidden permanently — `S` lists
every snoozed session with its wake time, and `lemonaid inbox snoozed` shows the
same list from the shell.

New agent output cancels a snooze early. Snoozing means "not this state, not
yet"; if the session produces something new, it wants you again.

## Jump by number

The first ten rows carry a number, shown before the session name. Pressing that
digit switches to the row, exactly as selecting it would.

The number is the row's position, so it renumbers whenever the list reorders —
it is a shortcut for the row in front of you, not a name a session keeps. Past
the tenth row there is no digit; scroll instead. Supporting more would mean
waiting after each keypress to tell `1` from `12`, and that delay would be paid
on every jump.

History is not numbered either. There Enter resumes rather than switches, and
a resume is too costly to hang on one unconfirmed keystroke.

The non-switchable table is not numbered. Those sessions belong to terminals
this one cannot switch to, so a number would name a row it cannot act on.

Set `jump_by_number = false` to leave the digits unbound.

## Undo

`z` reverses the last change you made to the inbox, and keeps going back through
earlier ones. Actions that only change a session's state are undoable — archive,
mark-read, snooze, rename. Actions that reach outside the inbox are not:
switching to a session and resuming one both do something to your terminal that
restoring a database row wouldn't take back.

Each undoable action shows a toast naming what it did, so an accidental archive
tells you what just disappeared instead of leaving you to guess. Undo history
lives for the lifetime of the TUI session and is not persisted, since a snapshot
stops being meaningful once other processes have written to the same rows.

## Configuration

Add a `[tui.keybindings]` section to your config:

```toml
[tui.keybindings]
quit = "q"
select = ""  # additional keys for select (Enter always works)
refresh = "g"
jump_unread = "u"
mark_read = "m"
mark_unread = "M"
archive = "a"
snooze = "s"
snoozed_list = "S"
pin = "p"
move_pin_up = "shift+up"
move_pin_down = "shift+down"
undo = "z"
rename = "r"
tmux_resume = "T"  # spawn tmux session from history
save_size = "H"  # save scratch pane size (follow mode)
flip_position = "f"  # move the scratch pane between top and left
jump_by_number = true  # digits 1-9,0 switch to that row
up_down = ""  # arrow key alternatives (see below)
```

For example, to use `o` for selecting sessions:

```toml
[tui.keybindings]
select = "o"
```

### Keys that carry a modifier

`move_pin_up` and `move_pin_down` name one key each, written the way Textual
writes it - `"shift+up"`, `"ctrl+k"`, `"K"`. They are the exception to the rule
below: their value is a single key name, not a set of one-character
alternatives. Set either to `""` to leave it unbound.

### Multiple keys per action

Each character in the string is a separate keybinding. For example:

```toml
quit = "qQ"  # both 'q' and 'Q' will quit
```

The footer shows the first configured key.

### Arrow key alternatives

The `up_down` field accepts a 2-character string for up/down navigation:

```toml
# Vim-style
up_down = "kj"

# Norman WASD-style (right hand)
up_down = "ri"
```

Leave empty (the default) to use only arrow keys.

## Non-configurable keys

- `Enter` - built into the DataTable widget
- `Escape` - always bound to quit (in addition to configured quit key)
- `P` - patch Claude binary (only shown when Claude is unpatched)
