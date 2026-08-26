# 0.18.0 (2026-08-25)

#### Added

- **Digits 1-9 then 0 switch to that session**, numbered from the top of the list. The number is the row's position and nothing else: it renumbers when the list reorders, so it is a shortcut for the row you can see rather than a name a session keeps.

  Only the first ten rows carry a digit; past that you scroll. A second digit would need a timeout to tell `1` from `12`, and that wait would be paid on every jump.

  The inbox only. In history Enter resumes rather than switches, and a resume is too costly to hang on one unconfirmed keystroke. The non-switchable table is unnumbered for the reverse reason: nothing there can be switched to at all. Set `jump_by_number = false` under the keybindings config to leave digits unbound.

#### Fixed

- **Read sessions are no longer bold.** The card headline styled the unread marker's slot whether or not there was a dot in it, and that style is bold. A colour change does not clear the bold attribute - only a reset does - so the bold from an empty marker carried forward into the session name, putting every row on the terminal's bold face regardless of its state.

- **The message is never bold**, on unread rows too. It is the one field that reads as prose rather than as a value to pick out, and a wrapped bold paragraph is harder to read than the plain one beside it.

- **A finished turn says "Waiting in ..." rather than "Stop in ..."**. Claude's `Stop` hook carries no notification type of its own, so it fell through to a fallback that prints the hook's name - leaking an internal event name into the inbox. It means the same thing `idle_prompt` does, and now reads the same way, matching what the codex and openclaw backends already said for a completed turn.

# 0.17.1 (2026-08-25)

#### Fixed

- **Binary patcher** now finds the notification polling interval in recent Claude Code versions (tested 2.1.234–2.1.246). The previous approach searched for `XXX=6000` within 500 bytes of `notificationType` in the binary, but the constant is defined far from that marker in these versions. The patcher keeps that proximity search as a first attempt and falls back to the hook module's constant trio (`600000, 30000, 6000`).

# 0.17.0 (2026-08-25)

#### Added

- **`lemonaid claude hooks` installs a SessionStart hook**, so a session records itself the moment it starts or is resumed. Every other Claude hook needs a turn, which meant a session you had not spoken to yet was invisible - and those are exactly the sessions a restore has to find. On the inbox this was written against, 20 agents were running and 8 were known.

  Opt-in, because it changes what the inbox holds: sessions that exist, rather than sessions that have said something. Sessions register as working and never as unread - one that has not spoken is not asking for anything, and a restore that flagged everything it started would be its own kind of noise. Editing `settings.json` is additive and idempotent; hooks you wrote are never touched, and `--uninstall` removes only lemonaid's own line.

  This is also what makes a restored session findable. Its identity (`session_id`, `cwd`) is durable; the pane it runs in is not. The hook re-reports the location on every resume rather than leaving it to be inferred from a tty.

- **`lemonaid tmux adopt` puts running agent panes into the inbox**, matching each to its conversation by working directory and most recent activity. A running pane is the one case where the facts restore needs can still be recovered - it is there to be asked - so sessions that predate the SessionStart hook do not have to stay invisible until each happens to notify. On the inbox this was written against, one run took restorable sessions from 5 to 11.

  Where the match is a guess it says so: several panes sharing a directory, two directories resolving to one conversation, or a conversation already running elsewhere in the inbox. `--skip-guesses` adopts only the unambiguous ones, and `--dry-run` writes nothing.

- **`lemonaid tmux doctor`** reports what a crash would cost while you can still do something about it: how many running agents the inbox knows about, how many sessions could actually be resumed, and which ones could not and why. `--unknown` lists running panes with no inbox row, and the report ends with the commands that would fix what it found.

  Every way restore fails is otherwise silent. A session whose transcript is no longer on disk looks restorable right up until `claude --resume` starts a fresh conversation instead, which does not report an error.

- **`lemonaid tmux scratch --restart`** replaces the `lma` process in the scratch pane without moving the pane. Killing it would discard what follow mode built around it - the pane sits in one of your windows, and every window it has visited holds a placeholder in its slot. The previous way to pick up new code was `prefix+: kill-pane` then `prefix+l`, which is that discard done by hand.

- **Enter on a running session in history returns it to the inbox** instead of starting a second copy beside the first. Archiving is a guess made from outside the session - a watcher that could not find its pane - and it is wrong often enough that history fills with sessions that never stopped. A session that really is gone still resumes exactly as before.

#### Fixed

- **The watcher asks the tmux server a session was recorded on.** A tmux command with no `-S` goes to whichever server the calling process is attached to, so a session on a different server was absent from that listing - indistinguishable from a pane that had been closed. A watcher running on one server archived live sessions running on another. Hooks now record `tmux_socket`; rows written before this have none and are checked exactly as they were.

  A socket naming a server that is gone exits non-zero, which reads as "cannot tell" rather than "no pane", so a server that never comes back does not archive everything it hosted.

- **A reused tty no longer resurrects an old session.** tty device names are recycled, so after a reboot a recorded tty usually names some unrelated pane, and every stale row claimed to still be running. Pane lookups now reject a tmux session younger than the record: on the inbox this was written against, that took archived rows falsely reporting themselves alive from 674 to 5. It narrows the lie rather than ending it, which is why the SessionStart hook reports the location rather than inferring it.


- **`lemonaid tmux restore` rebuilds the tmux layout from the inbox.** When tmux dies the sessions go with it, but the inbox does not - it still holds every active lemon and its cwd. What it never held was *where* each one was running, so rebuilding the layout after a crash was manual work. Notifications now record `tmux_session` and `tmux_window`, and `tmux restore` recreates each session, resuming every lemon in the window it occupied.

  Windows keep their recorded index, so a window lemonaid knows nothing about - an editor, a shell - comes back as an empty gap rather than shifting every later window down. Restored windows are not named: they pick up names from their processes, the same as they did before the crash.

  `--dry-run` prints the layout and starts nothing, which is worth doing first since restoring a day's work means starting many processes at once. Sessions are restored detached, and one that is already running is left alone rather than duplicated - after a crash you have usually rebuilt some by hand already. `--json` for both.

  Restoring goes through each backend's configured resume command, so this is not Claude-specific.

- **Notifications record which tmux session and window they belong to**, which is what makes the above possible. `get_tmux_session_name()` already existed, but its result was used only to derive a display name and then discarded.

  Recorded from two places, because a hook alone is not enough: an idle session's hook may not fire for days, and those are exactly the sessions whose window position is hardest to reconstruct after a crash. The hooks record it when they run, and the watcher - which already resolves panes by tty on each poll - keeps it current for every active session, in one `list-panes` call rather than one per session. Moving a window is followed; an unchanged location is not rewritten, and nothing else about the notification is touched.

  Locations are also carried forward across updates. Metadata is replaced wholesale, and a hook firing from a subprocess with no `TMUX_PANE` would otherwise erase the location that restore depends on.

# 0.16.0 (2026-08-25)

#### Added

- **Follow mode for the scratch pane**: the pane can stay visible across every window and session switch, so the inbox is ambient rather than something you summon. Enable with `lemonaid tmux scratch --follow`; `--unfollow` disables it. Nothing goes in `.tmux.conf`: showing the pane installs its hooks on the running server, and they run inside tmux itself (`if-shell -F`, `run-shell -C`) with no shell process.

  The pane is swapped between windows rather than moved: each window it has visited keeps a placeholder pane in its slot, so a window's own panes never resize when the scratch pane comes or goes, and nothing repaints on a switch. The first visit to a window is the only time its layout changes. Focus never rides along with the swap: a switch made from inside the inbox leaves the window you left focused on your own pane, and the inbox never arrives focused. A window left holding only a placeholder is closed (never a session's last window), and the slot keeps its saved size when the terminal is resized: a saved width is a character count, and it yields only when the client cannot hold it and still leave the main pane 40 columns.

  In follow mode `prefix+l` toggles focus between the scratch pane and your work rather than hiding it, and selecting a notification no longer dismisses the pane. `q` parks it until the next `prefix+l`.

  Pane height survives switches: resize it and press `H` to save, and the status row offers that only once your height has actually drifted from the saved one.

- **`scratch_height` and `follow_scratch` config** in `[tmux-session]`: the pane height in rows (default `10`), and whether new tmux servers get follow mode on first scratch-pane creation.

- **Sessions render as cards in a tall, narrow pane.** Each session is a card - name, time, cwd, branch, then the message wrapped onto as many lines as the pane can spare - instead of columns four characters wide. A left scratch pane is always cards and a top one always columns, whatever size tmux hands it at any instant; a plain `lma` decides from its shape (below 72 columns, or taller than 1.2x its width).

- **Clicking a session switches to it** on the first click, rather than moving the cursor and waiting for a second.

- **`LEMONAID_DB` points the inbox at a different file.** A second `lma` can run against invented sessions - a demo, a screenshot, an experiment - without either inbox's watchers archiving the other's rows. `scripts/demo-inbox.py` stages exactly that on a throwaway tmux server.

- **The bar above the list says whether anything is unread.** It turns the unread marker's own orange while the inbox has something waiting, and dark blue in session history. All three colours are ANSI, so the bar tracks the same terminal palette the rest of the TUI is drawn from.

- **Mark a session unread again**: `M` in `lma`, `lemonaid mark-unread --tty` for a tmux binding. It returns to the unread group at its existing age rather than jumping to the top.

- **Move the scratch pane between top and left without editing config.** `lemonaid tmux scratch --flip`, or `f` inside `lma`. The pane moves in whatever window it currently occupies, so a keybinding works from anywhere rather than only where you can see it. Each edge keeps its own size, so flipping back and forth doesn't lose either.

#### Fixed

- **One failed `tmux list-panes` no longer archives every live session.** A failed listing looked identical to "no pane has this tty", so the auto-archiver treated one tmux hiccup as every pane vanishing at once. The archiver now archives only when a pane is definitely gone.

- **One scratch pane per tmux server.** A lost state file used to mean a second `lma --scratch` process, with the first left running and painting a different idea of what was unread. The `@lemonaid_scratch` marker is now how the pane is found, and extra marked panes are killed.

- **Read rows are legible.** They were dimmed; most of the inbox is read most of the time, and dim on a dark background cost enough contrast that the pane stopped being readable. Bold-vs-plain still separates unread from read. History, which the dim had been telling apart, now has its own header colour, no marker column, and yellow rather than green timestamps.

#### Changed

- **A card spends one column on its gutter, not three.** The table's own cell padding is gone in card layout: the unread dot sits in the first column, the name one space after it, and the lines below take that single space of indent. The backend label (`CC`, `cx`) is right-justified against the pane's edge rather than left-aligned in a column of its own. On a 58-column sidebar that is four more columns of message per line.

- **Scratch pane height is rows, not a percentage.** The pane's saved height has always been read back from tmux as a row count, so a percentage could only ever be the initial default and the first save replaced it. Drift detection declined to compare percentages, which meant a percentage silently disabled the save-height hint. `--height` and `scratch_height` now mean rows.

- **Scratch pane state files renamed**: `scratch-pane-<server>.json` is now `tmux-scratch-<server>-pane` (plain text). Legacy files are cleaned up on first use.

# 0.15.0 (2026-08-07)

#### Added

- **`lemonaid for-lemons`** prints the guide for automated callers. An agent reaches lemonaid through the CLI and has no reason to know where a markdown file lives in a checkout it may not be sitting in, so the guide is installed alongside the package and reachable by command. `--path` prints its location instead. It is the same `docs/for-lemons.md` humans read, not a copy that can drift.

- **[Places](docs/places.md)**: `lemonaid place open <key>` gets you a session for something, acquiring its directory first if it doesn't exist yet; `lemonaid place toss` kills a session and releases the places it occupies. One command each way instead of two.

  `place open` is idempotent in the same spirit as `wt co` - it creates only when it has to, switches to an existing session rather than duplicating one, and neither case is an error - so you never have to know which situation you're in.

  **`place acquire <key>` gets the directory without a session**, printing where it is. That is what an automated caller wants: it has its own session, will never attach to a tmux one, and `place open` would leave an unused session behind for every worktree it created. Also idempotent - an existing directory is printed rather than re-created.

  Outside every root that has a key vocabulary, `place open <name>` is just a named session in the current directory, replacing `lemonaid tmux new -s <name>`. Where you are decides that, not whether a lookup happened to fail: inside such a root the name is always a key, so a typo acquires a directory rather than quietly becoming an empty session. A root with no `list` and no `path_of` claims no names, so being inside one reads the same as being outside every root. For these sessions the name is the identity rather than the directory, so two of them can share one.

  What "acquire" and "release" mean is a shell command you declare per repo root (`create`, `destroy`, `path_of`, `list`, `inspect`), so lemonaid still only knows about directories and terminals — it has no notion of a git worktree or any other scheme. Every hook is optional, so a plain clone coexists with a worktree repo and nothing has to detect which is which. The protocol is lines, not JSON, which is why `list` can be plain `git worktree list` piped through `sed`.

  **Teardown works on a session and everything it occupies.** Deleting a worktree and killing a session were each already one command; what was missing was anything that knew the two went together, so cleanup got put off until the context needed to do it well was gone. `place toss <key>` names the session sitting in that place and `place toss` uses the one you're attached to, but both resolve to the same set - so there is no form that kills a session while stranding a place it owned. The set is listed and confirmed before anything happens, which is where you decide whether the second worktree goes too. Either half may be absent: a session with no managed places just gets closed, and a place with no session - an `acquire`d directory nobody opened - is just released, which is the one form of toss that acts on exactly what you named.

  Ownership is derived from `tmux list-panes` when you ask, never recorded, so nothing can drift and a worktree an agent created resolves like any other. tmux keeps reporting a pane's original path after the directory is deleted, so a session that outlived its worktree still resolves and can still be closed.

  Two kinds of protection, neither overridable by `--force`. A root's `protected` keys (`main` and `master` by default) are never released, and never count as owned - everyone passes through the trunk worktree, and a confirmation line that can never be acted on is one you learn to skip past. `protected_sessions` under `[places]` refuses teardown of a session outright, for long-lived catchalls that aren't tied to one piece of work; it's global rather than per-root, since a session name isn't repo-scoped and the one you want to guard may not sit in a managed directory at all.

  `--yes` skips the confirmation, `--force` overrides an `inspect` hook reporting unpushed work - separate flags, so an agent can tear down unattended without also being able to discard commits.

  Teardown switches you out before destroying anything and does the slow part detached, logging to `~/.local/state/lemonaid/reap.log`. The session is killed before any directory is released, since a process holding a file there can make the removal fail.

  `place list --json` reports each place's key and its live tmux session name (empty when nothing runs there), so a caller can act on a listed place without deriving a key itself. Every command takes `--json`, so the same verbs serve a person at a prompt and an agent driving them. [docs/for-lemons.md](docs/for-lemons.md) documents the programmatic surface.

#### Changed

- **Enter on a session whose pane is gone now recreates it instead of doing nothing.** A tmux session dies for all sorts of ordinary reasons - `:kill-session`, a closed window, a reboot - and selecting one afterward used to silently fail, because the handler resolves a pane by TTY and gave up when nothing matched. The archive still records where that work was happening, so the session is now respawned from the `default` template in the same directory and switched to.

  This makes the inbox and history usable as a list of *places to pick work back up*, not only a record of where it happened. A dead session and a live one answer to the same key.

  Nothing is recreated if the directory itself is gone - a removed worktree, say. That reports a failure rather than spawning a session somewhere useless. Failures now raise a toast; the return value used to be discarded.

- `spawn_session_for_resume` is now `spawn_session`, with `resume_argv` optional: passing it replaces the window at `resume_window` as before, omitting it uses the template unchanged. `_auto_session_name` moved from `tmux/cli.py` to `tmux/session.py` as `auto_session_name`, removing a deferred cross-module import of a private name.

# 0.14.1 (2026-08-07)

#### Fixed

- **Codex rows stopped updating mid-turn.** The inbox writes a session's message only when the newest *describable* transcript entry has a new timestamp, and Codex's most common entries weren't described at all: it runs nearly everything through an `exec` tool that arrives as `response_item/custom_tool_call`, and puts turn boundaries in `event_msg` entries. Neither was handled, so a session could work for the better part of an hour while the row showed the last thing said before you replied. On one real session the newest described entry was 46 minutes stale, and coverage was 184 entries out of 1584.

  `custom_tool_call` now reports the command (parsed out of the `tools.exec_command({"cmd":...})` wrapper it's embedded in) or the file for a patch, and `event_msg` contributes `task_started`, `agent_message`, `patch_apply_end`, and `mcp_tool_call_end`. `task_started` matters most: it's the first entry after you send a message, so it's what moves the row off the previous turn. Same session, same file: 577 described, newest entry current.

  `should_dismiss` gained the same two entry kinds, so a notification clears when Codex resumes work rather than waiting for the next `reasoning` entry.

# 0.14.0 (2026-07-31)

#### Changed

- **The counts moved into the footer row.** "3 unread, 10 read" had its own row above the key hints, costing a row of list height for one short line. The key hints now show for 10 seconds at startup and then step aside, and the counts take that row. `?` toggles the hints back, and pressing it cancels the startup timeout so they stay up. Both use the same row, so the list is two rows taller than before.

  The patch-Claude hint and the history/snoozed counts share that slot, since they already replaced the same text.

#### Fixed

- **Blank line under the last session**. The responsive column sizing in 0.13.0 filled rows to the full terminal width, but a table long enough to scroll spends two of those columns on its vertical scrollbar. Rows came out one cell too wide for the space left over, and DataTable answered that overflow with a horizontal scrollbar - which rendered as an empty row between the list and the status bar and cost a row of list height, hiding a session. Column widths are now budgeted against the width the table can actually paint into, and reconciled against Textual's own measurement rather than an independent estimate of it.

# 0.13.0 (2026-07-30)

#### Added

- **Snooze** (`s`): hold a session out of the inbox until a chosen time - 15 minutes, 1 hour, 4 hours, tomorrow at 9am, or a custom duration (`45m`, `2h`, `3d`; a bare number is minutes). On expiry the session returns with the status it had when snoozed, so snoozing an idle session doesn't manufacture a notification. New agent output cancels a snooze early. `S` opens a snoozed view listing every snoozed session with its wake time; `lemonaid inbox snoozed` shows the same list from the shell.
- **Undo** (`z`): multi-level undo for inbox state changes - archive, mark-read, snooze, rename. Each action shows a toast naming the affected session, so an accidental archive says what it archived instead of silently removing a row. Actions with effects outside the inbox (switching to a session, resuming one) are deliberately not undoable. History is per-TUI-session and not persisted.

#### Fixed

- **No more scroll flash on refresh**. The inbox rebuilt every row on each one-second tick, which reset the cursor and scroll offset before restoring them a moment later - presenting as the list flashing to the top. Rows are now updated in place when the row set and its order are unchanged (the common case, where only a message or status moved), so the cursor and scroll position never move. A genuine row-set change still rebuilds, and keeps the cursor on its own row by key.

- **Name column sized for real titles**. Now that sessions carry sentence-shaped names, the fixed 14-char Name column truncated nearly all of them. Column widths are responsive: Name takes the largest share of flex space, and narrower terminals drop the columns that earn it least (TTY, then Branch and Message, which CWD largely duplicates) rather than starving Name. At 80 columns Name went from 14 to 39 characters. Rows now fill the terminal width exactly instead of overflowing horizontally.

- **Session names now use Claude's own conversation title**. Claude records the AI-generated name as `type: "ai-title"` entries in the session transcript (and `/rename` as `customTitle`), which lemonaid never read - so sessions kept the tmux worktree or cwd placeholder they were given at first prompt. Two things were wrong: the lookup only consulted `sessions-index.json`, which current Claude versions stopped maintaining (16 of 73 project dirs had one locally, none written in ~6 months), and the stored name was pinned at first sight and never revisited. The lookup now reads the transcript, and a placeholder is upgraded in place once a title exists - both when a hook fires and via a periodic background re-check in the TUI, since titles appear well after a session starts. A user rename still always wins; clearing it restores the newest title rather than the original placeholder.

  A Claude `/rename` takes precedence over the auto-generated title whenever it happened, including on a session that was already auto-titled - the two are now tracked separately, so a rename is recognized rather than being masked by an existing AI title. A name set inside lemonaid (`r`) still outranks both.

  The prior `session_name` hook-payload fallback (0.12.2) was dead code - that field is not present in Claude's hook JSON - and has been removed.

# 0.12.4 (2026-07-22)

#### Added

- **AskUserQuestion hook support**: the notify handler now recognizes `PermissionRequest` events (via `hook_event_name` fallback) and shows "Question in <path>" when Claude asks an interactive question mid-turn. Previously these went unnoticed since `Stop` doesn't fire for mid-turn questions. Documented recommended hook config with `PermissionRequest`/`AskUserQuestion` matcher.

# 0.12.3 (2026-07-21)

#### Added

- **Statusline: worktree branch mismatch warning**: branch name renders bold red when the current branch doesn't match the worktree it was created for. Detects mismatch by comparing the branch against the worktree metadata directory name from `git rev-parse --git-dir` (zero additional subprocess calls). Non-worktree repos are unaffected.

# 0.12.2 (2026-07-21)

#### Added

- **AI-generated session names in TUI**: the notify and submit hooks now read `session_name` from Claude Code's hook JSON (the AI-generated conversation title) and use it as a fallback when no custom title or `firstPrompt` is available. Sessions on `main` with generic cwd-derived names now get descriptive titles in the inbox.

#### Changed

- **Statusline: session name no longer truncated**: removed the 30-char truncation on session name display.

# 0.12.1 (2026-07-21)

#### Added

- **Statusline: model name**: shows the current model's display name (e.g. "Opus") dimmed after the context percentage.
- **Statusline: git dirty indicator**: appends `*` to the branch name when there are uncommitted changes to tracked files.
- **Statusline: session name**: shows the AI-generated or custom session name in dimmed parens at the end.

# 0.12.0 (2026-06-08)

#### Added

- **Sessions appear while working**: a new `lemonaid claude submit` hook (wired to Claude Code's `UserPromptSubmit`) registers a session in the inbox the moment you submit a prompt, as a read/working entry. Previously a session was invisible until its first `Stop` or permission prompt, so a long-running turn — especially in auto-accept mode, where permission prompts never fire — wouldn't show up until it paused for input. The registration never reorders or re-flags an existing session (`created_at` is preserved), and a prompt to an archived session brings it back as working.

# 0.11.3 (2026-04-16)

#### Fixed

- **Resume headless and remote-agent sessions**: Sessions started outside tmux/wezterm (e.g. via the Signal bridge, scheduled triggers, remote agents) now surface in the history view (`h`) regardless of read status, since they have no terminal to switch back to. Previously they were stranded in the non-switchable panel with no resume path.
- **Resume from any directory for agent-started sessions**: `find_session_project` now falls back to scanning `~/.claude/projects/` when a session isn't in `~/.claude/history.jsonl`. Sessions started by remote agents or scheduled triggers never touch history.jsonl, so both lemonaid and `claude --resume` itself couldn't locate them from another cwd.

# 0.11.2 (2026-04-07)

#### Added

- **Configurable resume commands per backend**: `[backends.<name>]` section in config.toml with a `resume_command` template. Placeholders like `{session_id}` are filled from notification metadata. Built-in defaults for claude, codex, openclaw, and opencode so existing configs work unchanged. Fixes the issue where `T` resume didn't pick up session-level flags like `--allow-dangerously-skip-permissions`.

#### Fixed

- **Tmux session naming from `T`**: Uses the notification/session name instead of deriving from the working directory. Avoids collisions when multiple sessions share a cwd.
- **Rename works in history mode**: The rename action (`n`) now operates on the selected history entry instead of silently targeting the hidden inbox table.

# 0.11.1 (2026-03-31)

#### Fixed

- **Versioned Python in tmux window titles**: Replaced enumerated `python3.10`–`python3.13` entries with a regex, so new Python versions (e.g. 3.14 for xonsh) are recognized without code changes. Versioned interpreters with no meaningful pane title (i.e. acting as a shell) now hide correctly instead of showing "python3.14".

# 0.11.0 (2026-03-24)

#### Added

- **`lemonaid claude resume <session-id>`**: Resumes a Claude session from any directory. Looks up the correct project directory from `~/.claude/history.jsonl` and `cd`s there before calling `claude --resume`. Solves the longstanding issue where `--resume` fails with "No conversation found" when run from a different directory than the original session. Also available as `lemonaid claude --resume <id>` so you can prepend `lemonaid` to a failing `claude` command. Extra flags like `--dangerously-skip-permissions` are forwarded. All TUI resume paths (Enter, `c`, `T`) now use this wrapper for Claude sessions.
- **Tmux session from history** (`T`): In history mode, press `T` to spawn a full tmux session around a historical lemon session. Uses the configured session template with the resume command replacing one window (configurable via `resume_window` in `[tmux-session]`, default 0). For Claude sessions, the tmux session roots at the correct project directory from history. Keybinding configurable via `tmux_resume` in `[tui.keybindings]`.
- **cwd drift warning**: The notify hook now logs a warning when Claude reports a different `cwd` than what's stored for an existing session, helping diagnose metadata mismatches.

#### Fixed

- **`tmux new` on fresh boot**: `base-index` is now queried after session creation so the tmux server exists. Previously, if `~/.tmux.conf` set `base-index = 1` and no tmux server was running, lemonaid would target window 0 (which doesn't exist).
- **`send-keys` failures non-fatal**: If sending a command to a window fails (e.g. wrong index), session creation continues instead of aborting — the session and remaining windows are still set up and attached.

# 0.10.2 (2026-02-23)

#### Fixed

- **Arrow keys now navigate into non-switchable table**: Cross-table jumping (arrow down from main → non-switchable, arrow up back) was only wired to custom vim-style keys, not the actual arrow keys.

# 0.10.1 (2026-02-23)

#### Changed

- **`tmux new` auto-naming**: Session name is now auto-derived from the last one or two directory components (e.g. `~/play/lemonaid` → `play-lemonaid`). The positional name argument is replaced with `-s` flag, matching tmux's own convention.

# 0.10.0 (2026-02-19)

#### Added

- **OpenCode integration**: Added first-class OpenCode support with `lemonaid opencode notify` / `dismiss`, OpenCode docs, tmux process labels, and TUI resume support (`opencode --session ...`).
- **OpenCode watcher behavior**: Notifications now auto-transition based on activity: unread on turn completion (`step-finish` with `reason: "stop"`) and read when session activity resumes.
- **OpenCode channeling**: OpenCode notifications now key by full session ID (`opencode:<full_session_id>`) to avoid collisions between sessions sharing the same ID prefix.

# 0.9.0 (2026-02-16)

#### Added

- **Bootstrap command**: `lemonaid claude bootstrap` retroactively imports historical Claude sessions (from before lemonaid was installed) into the archive. Scans `~/.claude/projects/*/sessions-index.json` and imports sessions with their original timestamps, names, and metadata. Use `--dry-run` to preview.
- **Summarize command**: `lemonaid claude summarize` generates concise names for sessions with poor names (truncated first prompts) using `claude -p --model haiku`. Reads the first few transcript messages for context. Runs in parallel for batch operations.

# 0.8.0 (2026-02-11)

#### Added

- **Remote OpenClaw sessions via SSH**: Session files on a remote host can now be monitored by setting `[openclaw] remote_host` in config. The watcher reads session tails via SSH; registration discovers sessions on the remote host. Recommend SSH ControlMaster for connection reuse. See `docs/openclaw.md`.
- **Backend-provided reader**: Watcher backends can now override `read_lines()` to customize how session files are read (used by OpenClaw for SSH).

# 0.7.1 (2026-02-12)

#### Changed

- **Configurable backend labels**: The emoji icons for Claude/Codex/OpenClaw in the TUI are replaced with text labels. Defaults to the backend name; override via `[tui.backend_labels]` in config.
- **Config reference doc**: Added `docs/config.md` as a central index of all config options.

# 0.7.0 (2026-02-11)

#### Added

- **Session history**: Press `h` to browse archived sessions. Filter with `/`, resume with Enter. In non-scratch mode, Enter replaces the current terminal with the resumed session (`claude --resume`). In scratch mode or with `c`, the command is copied to clipboard.
- **Git branch in metadata**: Notification hooks now record the git branch, displayed in the history view.
- **CWD and branch columns**: Both main and history views now show CWD (fish-shell style abbreviation) and git branch.
- **Purge command**: `lemonaid inbox purge [--older-than DAYS]` for manual cleanup of old sessions (default 90 days).

#### Improved

- **DataTable full-width**: Tables now stretch to fill the terminal width with proportional flex columns.
- **Unified column layout**: Main and history views share the same columns — no visual jumping on toggle.
- **Logging**: Switched to Python `logging` module; all components write to `/tmp/lemonaid.log` with hierarchical logger names.

# 0.6.2 (2026-02-11)

#### Fixed

- **Rename persistence**: User-set session names via the TUI rename action now survive notification upserts. Previously, every hook firing (idle, turn-complete, etc.) would overwrite the custom name with the auto-detected one.

# 0.6.1 (2026-02-11)

#### Fixed

- **Non-switchable sessions in lower pane**: Sessions without a matching `switch_source` (NULL or different env) now always appear in a separate non-switchable section instead of mixing into the main table. Replaces the `show_all_sources` config option.
- **Stale session cleanup across all sources**: Watcher now checks all sessions for dead panes/processes, not just those matching the current environment.
- **Navigable non-switchable pane**: Arrow keys flow between main and non-switchable tables; archive/mark-read work on both, but Enter/select is blocked on non-switchable sessions.
- **Smart timestamps**: Sessions older than 24 hours show date instead of time.

#### Removed

- `show_all_sources` TUI config option (non-switchable sessions are now always shown)

# 0.6.0 (2026-02-03)

#### Added

- **OpenClaw integration**: New watcher backend for [OpenClaw](https://openclaw.ai/) sessions. Detects turn completion via `stopReason: "stop"` in transcripts and marks notifications as needing attention. See `docs/openclaw.md` for setup.
- **Mark unread support**: Watcher can now mark notifications as unread when an agent completes and is waiting for user input.

#### Fixed

- **Flip-flop prevention**: When marking a notification as unread, `created_at` is updated to the current time. This prevents the watcher from immediately marking it read again based on old transcript entries.

# 0.5.0 (2026-01-26)

#### Added

- **Show all sources**: New `show_all_sources = true` TUI config option shows sessions from other terminal environments (e.g., wezterm sessions when in tmux) in a separate non-interactive section below the main table. Lets you monitor all sessions without cluttering navigation.
- **Auto-archive dead panes**: Watcher now archives notifications whose panes no longer exist, in addition to process exit detection.

#### Changed

- **Switch-source based handlers**: Handler selection now uses the notification's `switch_source` (where it came from) instead of channel pattern matching. Built-in handlers (tmux, wezterm) are auto-selected based on switch-source. No `[handlers]` config needed.
- **Renamed `terminal_env` to `switch_source`**: The database column and API field are renamed to better reflect the concept: the switch-source determines which switch-handler can navigate back to the notification's origin.
- **Renamed `detect_terminal_env()` to `detect_terminal_switch_source()`**: More explicit naming.
- **Removed `exec:` handlers**: Will be reintroduced as hooks in a future release.

#### Migration

- Database migration automatically renames the `terminal_env` column to `switch_source`

## 0.4.10 (2026-01-26)

#### Changed

- **Watcher uses transcript timestamps for caching**: Watcher now caches the timestamp of the last transcript entry processed (not just the message string). This allows proper detection of new activity vs. polling the same state. When timestamp is unchanged, watcher doesn't overwrite DB - this preserves legitimate "Permission needed" messages while still updating when Claude makes progress.

## 0.4.9 (2026-01-26)

#### Changed

- **Better watcher logging**: Log entry type and timestamp when marking notifications as read. Log existing state when upserting notifications. Helps debug permission prompt flapping.

## 0.4.8 (2026-01-26)

#### Fixed

- **Git worktree support**: Watcher now finds Claude session transcripts when working in git worktrees by searching parent directories for the Claude project path.
- **Encoding resilience**: Watcher no longer crashes on malformed UTF-8 in session files.

## 0.4.7 (2026-01-24)

#### Added

- **Configurable select key**: New `select` keybinding option (e.g., `select = "o"`) adds additional keys for selecting a session. Enter always works regardless of config.

## 0.4.6 (2026-01-24)

#### Changed

- **Smarter scratch pane toggle**: `prefix+l` now selects the scratch pane if it's visible but not focused, instead of hiding it. Press again when focused to hide. This makes the keybinding more idempotent - pressing it always gets you to the scratch pane.

## 0.4.5 (2026-01-24)

#### Added

- **Configurable keybindings**: All TUI keybindings can now be customized in `config.toml`. Each action can have multiple keys (e.g., `quit = "qQ"`), and arrow key alternatives can be set for up/down navigation (e.g., `up_down = "kj"` for vim-style).

## 0.4.4 (2026-01-24)

#### Added

- **Rename sessions from TUI**: Press `r` to rename any session directly in the inbox. Enter a custom name or clear to revert to auto-detected naming. Names persist and survive session updates.

#### Changed

- **TUI modularized**: Split monolithic `tui.py` into `tui/` package with separate modules for app, screens, and utilities.

## 0.4.3 (2026-01-24)

#### Added

- **Auto-archive on session exit**: Sessions are now automatically archived when the watcher detects the Claude/Codex process is no longer running on its TTY. No more stale sessions lingering in the inbox.

## 0.4.2 (2026-01-24)

#### Fixed

- **TUI startup speed**: Fixed ~2 second delay on TUI startup by moving Claude binary patch check to a background thread.

## 0.4.1 (2026-01-24)

#### Added

- **Claude statusline**: Optional `lemonaid-claude-statusline` command for Claude Code's `statusLine` setting. Shows time, elapsed since last message, git branch, context window usage (with color gradient), and vim mode.

#### Fixed

- **Scratch pane first-launch**: Fixed issue where the scratch pane required two key presses on first launch. The cause was `tmux new-session` changing the implicit "current pane" context; now we capture and explicitly target the original pane.

# 0.4.0 (2026-01-24)

#### Added

- **Codex support**: Notifications and live activity updates for Codex CLI sessions.
- Unit tests for shared watcher utilities and Codex watcher activity parsing.

#### Changed

- Consolidated Claude/Codex watcher logic into shared `lemon_watchers` utilities while keeping backend-specific code in their packages.

# 0.3.0 (2026-01-24)

#### Added

- **Real-time activity updates**: The message column now updates continuously as Claude works, showing the current tool being used (e.g., "Reading main.py", "Running pytest", "Searching for pattern"). Updates happen for all active sessions, not just unread ones.

#### Changed

- Watcher now polls all active sessions (not just unread) to provide live activity feedback
- Separated "mark as read" from "update message" - marking happens on first activity, messages update continuously

## 0.2.3 (2026-01-23)

#### Fixed

- Scratch pane window now named "lma" instead of hostname:lemonaid
- `lma` command now sets terminal title to "lma" (was missing, causing window status to show hostname)

## 0.2.2 (2026-01-23)

#### Changed

- **Scratch mode**: `q`/`Escape` now hides the pane instead of quitting, keeping lma alive for instant re-toggle

## 0.2.1 (2026-01-23)

#### Added

- **Jump to unread** (`u`): New keybinding to jump directly to the earliest unread session without navigating through the list

# 0.2.0 (2026-01-23)

#### Added

- **Scratch pane**: Toggle a persistent `lma` pane with `lemonaid tmux scratch`. The pane stays running in the background for instant show/hide without startup delay. Auto-dismisses after selecting a notification.
- `lma --scratch` flag for running in scratch mode (auto-hide after selection)

## 0.1.1

#### Added

- `tui.transparent` config option for terminal transparency support
- Notification names derived from tmux session name automatically

#### Fixed

- Various tmux color improvements

# 0.1.0

Initial release with core features:

- **Inbox TUI** (`lma`): View and manage notifications from Claude Code and other tools
- **Notification system**: Receive notifications via `lemonaid claude notify` hook
- **tmux integration**: Switch to notification source, back-navigation, session templates
- **WezTerm integration**: Alternative to tmux with similar features
- **Window status**: Colorized tmux window titles based on directory/process
- **Claude Code patcher**: Reduce notification delay from 10s to 100ms
- **Mark as read**: `prefix + m` keybinding for tmux
- **Unread indicators**: Visual distinction for unread notifications
- **Session templates**: Create tmux sessions with predefined window layouts
