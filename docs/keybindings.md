# TUI Keybindings

All keybindings in the `lma` TUI are configurable via `~/.config/lemonaid/config.toml`.

## Default Keybindings

| Key | Action |
|-----|--------|
| `Enter` | Open notification (switches to that session). A click does the same, except clicking the selected row for the lemon already behind the focused scratch pane keeps focus in the inbox. On a group's header, collapse the group or open it |
| `1`-`9`, `0` | Switch to that session in the list, counting from the top; group headers aren't counted |
| `u` | Jump directly to earliest unread session |
| `Ctrl`+`a` / `Home` | Move to the top row of the list, pins included |
| `Ctrl`+`e` / `End` | Move to the bottom row of the list (see below) |
| `m` | Mark as read |
| `M` | Mark as unread again |
| `a` | Archive (remove from list) |
| `s` | Snooze session (pick a duration) |
| `S` | Toggle snoozed view |
| `w` | Show or hide the folded sessions, when `[tui] fold_statuses` is set |
| `N` | Show or hide your notes under the sessions, when `[tui] notes` is set |
| `p` | Pin the session below any other pins, or unpin it |
| `Shift`+`↑` / `Shift`+`↓` | Move a pinned session up or down one slot; on a group's header, move the group |
| `z` | Undo the last inbox change |
| `r` | Rename session (clear to revert to auto-name) |
| `Tab` | Collapse or open the group of the row under the cursor, its header or one of its lemons |
| `b` | Show the session's brief in the left sidebar when available, otherwise a popup (see below) |
| `R` | Resume the selected detached session when available |
| `H` | Save scratch pane size (follow mode, only when it has drifted) |
| `f` | Move the scratch pane between top and left |
| `h` | Toggle history view |
| `/` | Search inbox and archived sessions as you type; in history, filter archived sessions |
| `g` | Refresh |
| `?` | Toggle the key hints (see below) |
| `q` / `Escape` | Quit |
| `↑` / `↓` | Navigate list |

Rows retained after their terminal pane closes show a `detached` marker. When the
saved session details are insufficient to resume one, its marker also says
`resume unavailable`. Enter, click, and `R` attempt to resume a detached row.
An unavailable terminal never removes a row from brief navigation: up/down
keeps its brief visible, with instructions for resuming. Resume error dialogs
stay open until Escape or Enter, so continued arrows do not dismiss them.
For tmux, resuming opens a new window in
the recorded session when its identity still matches. If that identity is no
longer available, it uses the session only when the saved directory identifies
exactly one. Otherwise, a dialog shows the resume command and lets you copy it
to paste into the session you choose. It never starts another tmux session.

If a Claude or Codex session's directory has been removed, the resume command
uses its nearest surviving parent directory. Claude loads the saved transcript
by its path; Codex receives an explicit `--cd` override. The conversation is
preserved, but the deleted directory and its files are not recreated. Restore
the directory through your configured place commands if you need its files.

The key hints occupy the bottom row for the first 10 seconds, then hand it back to
the unread/read counts. `?` brings them up again and cancels that timeout, so they
stay until you press `?` a second time. `?` is not configurable.

`Ctrl`+`e` stops at the last row you can see. A folded group stays folded, and the
lower table of sessions from other terminals is skipped, since none of them can be
switched to. In history and the snoozed list the two keys move within that list. In a
search box or a dialog, `Ctrl`+`a`/`Ctrl`+`e` and `Home`/`End` move the text cursor as
usual, and a brief view leaves them to its own scrolling.

### History mode

When a session has an attached brief, its status appears after its name.

| Key | Action |
|-----|--------|
| `Enter` | Resume selected session (replaces current terminal; from the scratch pane, see below) |
| `c` | Copy resume command to clipboard |
| `T` | Spawn a tmux session around the selected session |
| `/` | Filter by name, cwd, branch |
| `h` | Exit history |

From the tmux scratch pane, `Enter` opens the session in a new window of its
recorded tmux session, or of the one session working in its directory, and
switches there. When no such session exists it starts one, as `T` does. The row
returns to the inbox on its new pane. If the resume cannot start, a dialog says
why and offers to copy the command.

### Search mode

Press `/` from the inbox to filter session and attached brief names, messages, channels, directories, and branches. Matching inbox rows keep their order and formatting; nonmatches disappear as you type. Inbox matches fill the list first. When space remains, archived matches appear below a divider; the bottom line counts both sections even when the archive is hidden. Enter or Down moves from the search box to the inbox matches, and Down from the last inbox match moves to the archive when shown. Enter switches an inbox session or resumes an archived one. Escape restores the full inbox.

### Snoozed mode

| Key | Action |
|-----|--------|
| `Enter` | Wake the selected session now (returns it to the inbox) |
| `S` / `q` | Back to the inbox |

## Brief

When the scratch pane follows on the left, `b` shows the selected lemon's brief
in place of the inbox without leaving the inbox pane. Up/down arrows (or the configured
`up_down` keys) move between briefs. Each brief is drawn at once and the main pane
follows it to that lemon a moment later, while focus stays on the brief. A dot before
the lemon's name means its inbox entry is unread; `m`, `M`, `r` and `z` mark it read,
mark it unread, rename it, and undo, as in the list. `q` or `Escape` restores the inbox. `prefix+b` toggles
the brief from the lemon pane, and switching windows or sessions restores the inbox.
`prefix+l` focuses the scratch pane and keeps the brief; use the mouse wheel to scroll
the brief while staying in the lemon pane.

Otherwise, `b` opens a tmux popup over your client. Both views start each lemon with its inbox
card, opened up: name and model, then tmux location, directory and branch, then status, brief age,
and each `PR #N` or pull-request URL in the brief, with its live state (`open`, `draft`, `merged`,
`closed`) when [`[brief] pr_state`](config.md#brief) is set. The card uses the inbox's colours, including the filled headline for `alert`, `blocked`,
`merge`, `approve`, `review`, `done` and `running`. Below it come the brief's `Needs` part in the attention colour, then the rest of
`## Now` with `Done` last (or an older session's `.z/brief.md`), the rest of the brief below a
rule, and the brief's path at the bottom.

Bare `.md` paths under an Obsidian vault in [`[brief] vaults`](config.md#brief) open in
Obsidian, and bare
`https://` and `obsidian://` URLs are shortened to a label (`lemonaid#74`, a note's name). Each
label is a terminal hyperlink (OSC 8) in its own colour, so cmd-click opens it from any line it
wraps onto; tmux passes hyperlinks through when `terminal-features` includes `hyperlinks`. A plain
click on a link in the sidebar, in text, a heading or a table, opens it with `open` (`xdg-open` off macOS), which sends each scheme
to the app registered for it. Markdown links and code
spans are left as written.

A session with several lemons, opened from a window with none, starts with the session's name as a
yellow bar, then one card for every lemon recorded in it, located by window (`w2`). A lemon
without an attached brief uses the `.z/` brief named for it, or an unclaimed `brief.md`, and
otherwise says it has none. The lowest-numbered window's
lemon shows its whole `## Now`, the others only their `Needs` and one line each of `Running` and `Waiting on`.


### Questions

A brief can explain what its lemon needs from you in a `## Questions` section after
`## Now`: one `###` entry per `Needs` bullet that asks something, named with that bullet's
label. A bullet's label is its text up to its first colon, or the whole bullet, ignoring
bold and case, so `- **retry policy:** which one?` is explained by `### retry policy`.
Both views show each entry under its bullet, and mark the first question selected with `▶`.
Bullets with no entry, and briefs with no `## Questions`, show as before.
An entry whose heading matches no Needs bullet appears as a warning in the brief view;
`brief check` reports the same mismatch.

| Key | Action |
|-----|--------|
| `[` | Select the previous question |
| `]` | Select the next question |
| `a` | Answer it: type one line, Enter sends it, Escape cancels |
| `Y` | Send `Yes, approved` for the selected question immediately |
| `d` | Ask the lemon for more detail |

An answer goes to the brief's lemon the way `lemonaid tell` sends it, as
`Answer to <label>: <text>`, from your `$USER`. When the brief's Status is `blocked`,
`alert`, `merge` or `approve`, the answer ends with a line naming what else is under `Needs`, so the
lemon remembers to update its Status. More detail sends
`More detail needed on <label>: rewrite that entry in ## Questions`. Neither needs tmux,
and a lemon not running yet gets them when it starts. A line along the bottom of the view
names the keys whenever the brief has questions. The five are set by `question_previous`,
`question_next`, `answer`, `answer_yes` and `more_detail`, each one key (see
[Keys given by name](#keys-given-by-name)).

Press `q` or `Escape` to close the popup. `lemonaid brief
show <session> --popup` uses the same sidebar-or-popup behavior from any pane, and can be bound to a tmux key (see [tmux.md](tmux.md#brief-view)). The popup has a yellow border and uses 90% of the
client width up to a 140-column maximum.

## Snooze

`s` holds a session out of the inbox until a time you pick. Type a duration
straight away (`45m`, `2h`, `3d`, `1w`, or `morning`; a bare number means
minutes) and press Enter. Days and weeks count mornings: `1d` wakes at the next
09:00, `3d` at the third. With the box empty, Enter takes the highlighted
preset: 30 minutes, 3 hours, 1 day, or 4 days. Up and Down move the highlight.
`[inbox] snooze_presets` and `snooze_day_starts` change the presets and the
09:00 (see [config.md](config.md#inbox)).

When the timer expires the session returns with the status it had when you
snoozed it: one that was demanding attention comes back unread, one that was
merely idle comes back read. Nothing is ever hidden permanently — `S` lists
every snoozed session with its wake time, and `lemonaid inbox snoozed` shows the
same list from the shell.

New agent output cancels a snooze early. Snoozing means "not this state, not
yet"; if the session produces something new, it wants you again.

A lemon can snooze its own row with `lemonaid inbox snooze --self 2h` (or
`morning`, or `--clear`), in the same syntax. That snooze lasts through the
lemon's turn ends, since the lemon sets it mid-turn; a permission prompt or a
question still wakes it. See `docs/for-lemons.md`.

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
first = "ctrl+a"  # the top row; Home always works too
last = "ctrl+e"  # the bottom row; End always works too
undo = "z"
rename = "r"
brief = "b"  # show the session's brief
brief_key = ""  # a second key for brief, as a key name
group_key = "tab"  # collapse or open the group the cursor is in
history = "h"  # toggle history view
search = "/"  # search inbox and archive sessions; filter in history
copy_resume = "c"  # copy resume command (history)
tmux_resume = "T"  # spawn tmux session from history
resume_detached = "R"  # resume a detached inbox row
save_size = "H"  # save scratch pane size (follow mode)
flip_position = "f"  # move the scratch pane between top and left
fold = "w"  # show or hide folded sessions (needs [tui] fold_statuses)
notes = "N"  # show or hide your notes (needs [tui] notes)
question_previous = "["  # in a brief view, the previous question
question_next = "]"  # in a brief view, the next question
answer = "a"  # in a brief view, answer the selected question
answer_yes = "Y"  # in a brief view, send "Yes, approved" immediately
more_detail = "d"  # in a brief view, ask for more detail on it
jump_by_number = true  # digits 1-9,0 switch to that row
up_down = ""  # arrow key alternatives (see below)
```

For example, to use `o` for selecting sessions:

```toml
[tui.keybindings]
select = "o"
```

### Keys given by name

`brief_key`, `group_key`, `move_pin_up`, `move_pin_down`, `first`, `last`, `question_previous`, `question_next`, `answer`,
`answer_yes` and `more_detail` name one key each, written the way Textual writes it - `"tab"`,
`"shift+up"`, `"ctrl+k"`, `"K"` - or as the character itself (`"("` is
`"left_parenthesis"`). They are the exception to the rule below: their value is a single key
name, not a set of one-character alternatives. Set any of them to `""` to leave it unbound.

Loading the config warns on stderr when one key is bound to two actions in the inbox list
or in the brief view, the `up_down` keys and arrows included. The question keys act only in
a brief view, so `a` answers there and archives in the list.

`group_key` defaults to `Tab`. Set `brief_key = "tab"` and `group_key = ""` instead,
and a tmux binding which opens the scratch pane can be followed by Tab to reach the
brief. Either way Tab is taken before Textual's own focus-next, except in the snooze, rename and help dialogs and in the history
filter, where it still moves focus.

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
- `Home` / `End` - the top and bottom of the list, alongside `first` and `last`
- `P` - patch Claude binary (only shown when Claude is unpatched)
