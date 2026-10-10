# 0.95.0 (2026-10-09)

#### Added

- **`lemonaid tell` starts a recipient that won't read the message.** A lemon whose harness exited is resumed in a new window of its tmux session, and an idle Claude with no inbox waiter is prompted, both to read their inbox; each start is posted to the inbox. A lemon whose brief says `done`, or whose row is archived, is left alone, and the sender gets its Status, its `## Now` and the command to resume it. `[messages] autoresume` (`on`, `off`, `claude`, `codex`) chooses which harnesses are started.
- **`tell` stops starting a lemon that keeps dying.** After `autoresume_max` starts (default 3) within `autoresume_window` (default `"20m"`), the sender is told the lemon is crash-looping and an alert goes to the inbox. A lemon dead again within three minutes of a start counts that start twice.

# 0.94.0 (2026-10-09)

#### Changed

- **`lemonaid tell` says whether the recipient will read the message, and exits 1 when it won't.** A lemon whose harness has exited is `dead`; an idle Claude lemon with no inbox waiter is `deaf`. The message is still queued for when it comes back.

# 0.93.0 (2026-10-09)

#### Added

- **`lma` draws each group under a header line, placed by its most pressing row's status, above single lemons of that status.** `Enter` on a header, or `Tab` on it or any of its lemons, collapses the group, and a collapsed header takes the colour of its most pressing row's status, and a dot when a row is unread; `Shift`+`↑`/`↓` move it. A pinned lemon in a group heads it and stays visible when it's collapsed. In the sidebar a group's cards sit one column in, behind an unbroken rail in the group's colour. The focused lemon's green bar on a card is now the same half block. A lemon in two groups appears in both. A folded lemon in a group is hidden inside it, and the header counts `(2/3)`: two active of three.

#### Changed

- **`Tab` collapses and opens groups instead of showing the brief** (new `group_key`; `brief_key` now defaults to none). `b` still shows the brief, and `brief_key = "tab"` with `group_key = ""` restores the old Tab.

# 0.92.0 (2026-10-09)

#### Added

- **`lemonaid group` names sets of lemons: `create`, `add`, `remove`, `rename`, `delete`, `list` and `sync`.** A child joins its parent's groups when `brief new --child` writes its brief, or when `place open` or `lemon start` starts it with `--parent`; `--group` names others instead. Each member brief gets a `Groups:` line, read in when its Brief-ID is new to a database, so groups follow a brief to another machine; `brief check` reports a line that disagrees.

# 0.91.0 (2026-10-09)

#### Added

- **`lemonaid watch briefs --children --orphans` also watches briefs no live lemon owns,** meaning briefs with no parent link or whose parent's session is gone. It wakes on `blocked`, `alert`, `merge`, `approve`, `review` and `done` by default (`--to` replaces the set), and on a new or changed Needs ask.

# 0.90.2 (2026-10-09)

#### Fixed

- **A waiter stopped by SIGTERM now says who stopped it.** It names the lemon and pid when `lemonaid watch stop` sent the signal, and says the signal came from outside lemonaid (a `kill`, a `pkill` pattern or the harness) otherwise; both go to the lemonaid log too.

# 0.90.1 (2026-10-09)

#### Fixed

- **A lemon can stop its own waiters without stopping everyone else's.** `lemonaid watch stop --self` stops all of the caller's waiters of every kind, or one named by kind and target, and removes them from its brief's `## Waiters`; the `pkill -f "lemonaid inbox watch --self"` lemons used instead killed every lemon's waiter on the machine. A waiter stopped by SIGTERM now says so and prints its rearm command, where it used to exit with no output.

# 0.90.0 (2026-10-09)

#### Added

- **Inbox rows can show each Claude and Codex lemon's context use, as a percentage of a threshold you set in `[tui.context_threshold]`.** It is off until configured. The threshold is per backend or per model, as a share of the window (`"50%"`) or a token count (`"0.65M"`). The number's colour runs from purple through blue to red at the threshold, and on to magenta past it. Claude's window comes from `lemonaid-claude-statusline`, which now saves it per session.

# 0.89.5 (2026-10-09)

#### Fixed

- **Resuming an archived session from the scratch pane starts it.** It used to only copy the resume command, and the row went back to the archive a second later; it now opens in a tmux window and stays in the inbox, and a failure says why.

# 0.89.4 (2026-10-08)

#### Fixed

- **A Codex lemon started by lemonaid in a workspace-write sandbox can write the lemonaid database and state directories, so `lemonaid tell` works there.** Add other directories it must write, such as a folder of review documents, to `codex_writable_roots` in `[tmux-session]`.

# 0.89.3 (2026-10-08)

#### Fixed

- **`lemonaid brief handoff --to claude` no longer times out when the outgoing lemon is Codex.** Once the ready marker is seen the Codex session is terminated, since it cannot exit itself, and stays resumable by session id.
- **A `## ` line inside prose no longer ends the `## Handoff` section early,** and `lemonaid brief check` flags a heading line with an unpaired backtick.

# 0.89.2 (2026-10-08)

#### Fixed

- **`lemonaid usage --watch` no longer repeats a step alert or alerts again when a lower reading follows a higher one.** A step now alerts once per limit window and re-arms only when the window resets.

# 0.89.1 (2026-10-08)

#### Changed

- **`place toss` accepts routine confirmations by default and declines plans that show unusual work or side effects.**

# 0.89.0 (2026-10-08)

#### Added

- **`lemonaid usage` shows Claude and Codex subscription usage, and `--watch` blocks until an alert.** It alerts on each 20% step and when pace projects running out before the reset; thresholds are set in `[usage]`. On a terminal the summary colors each window's usage by pace and its projection at reset by how close it comes to the cap (`--no-color` disables it). `lemonaid-claude-statusline` now saves the `rate_limits` Claude Code passes it, which is where Claude usage comes from.

# 0.88.1 (2026-10-08)

#### Fixed

- **`place toss` scopes same-named cleanup to the root identified by pane paths.** Ambiguous matches stay unreleased with a reason in JSON and unattended text; unrelated lookup failures no longer block cleanup.

# 0.88.0 (2026-10-08)

#### Changed

- **`place toss` retires a tmux workspace first, with directory cleanup through configured hooks.** Sessions without managed directories are ordinary targets. Interactive bare toss selects the current session; unattended calls must name it. Hybrid workspaces whose lemons occupy unrelated places are refused. Sessions without identifiable lemons release a directory only when their work panes consistently occupy it. Protected or shared directories stay.

# 0.87.0 (2026-10-08)

#### Added

- **`watch pr --ci` wakes on CI completion, passing or failing.** The packaged `watch-pr` skill explains when to let CI validate a small change and keep the completion watch armed.

# 0.86.1 (2026-10-08)

#### Changed

- **`place toss` names lemons awaiting action in its confirmation, in their inbox status colors.** Enter declines the toss.

# 0.86.0 (2026-10-07)

#### Added

- **A packaged `brief` skill explains brief upkeep, statuses, waiters, child cleanup checks, and reviewer startup.** Install it with `lemonaid skills install`, or preview it with `lemonaid skills install --print brief`. The watch skills explain automatic recording and permanent removal.
- **Doc, PR, file, and child-brief watches record their restartable commands in the attached brief (the explicit Codex recipient’s, or otherwise the caller’s).** Recorded commands keep their supplied arguments without injected defaults or temporary state paths. Rearms update the same entry using its original directory and repository context, preserving it between one-shot events. Custom waiters can still use the manual brief verbs.

# 0.85.1 (2026-10-08)

#### Fixed

- **Detached inbox rows resume on click or Enter, and remain reachable while browsing briefs.** An unavailable terminal leaves its brief visible with recovery instructions.
- **Claude and Codex conversations can resume after their working directory is removed.** They use the nearest surviving parent directory, with the saved conversation intact.

# 0.85.0 (2026-10-08)

#### Added

- **`[brief] name` names new lemons with a shell command instead of a WordyBin.** `brief id --reroll` asks it too, and `--set` then takes any name of letters, digits, `_` and `-`.

# 0.84.0 (2026-10-07)

#### Added

- **`watch briefs --children --to STATUS` selects which destination statuses wake the parent.** Repeat it for multiple statuses; Needs-only changes stay quiet with this filter.

#### Changed

- **Child brief watches default to waking only on entry into `merge` or `done`.** Other Status changes and Needs-only changes advance the saved state without waking.

# 0.83.1 (2026-10-08)

#### Fixed

- **`place toss` leaves terminal rows to the watcher, preserving lemons and pins in surviving panes.** Direct archiving is limited to Codex daemon rows in directories being released.

# 0.83.0 (2026-10-07)

#### Added

- **`lemonaid watch briefs --children --self` wakes a parent when a child's Status or Needs ask changes.** Rearms catch changes between waiters without repeating delivered events; Claude and Codex delivery and a `watch-briefs` skill are included.

# 0.82.0 (2026-10-07)

#### Changed

- **`watch pr --comments` includes outdated and resolved review threads.** Use `--skip-outdated`, `--skip-resolved`, or their `[watch.pr]` defaults for quieter waits.

# 0.81.0 (2026-10-07)

#### Added

- **`lemonaid go <Lemon-ID | channel>` jumps directly to a lemon's tmux pane.** `--link` prints a clickable `lemonaid://go/...` link, with macOS handler setup documented in `docs/go.md`.

#### Fixed

- **After a link jump, clicking the inbox's selected row returns to its lemon.** The green active marker belongs to the latest notification from each focused terminal, so older rows sharing its TTY do not also appear active.

# 0.80.0 (2026-10-07)

#### Added

- **Per-root `project_name` hooks name projects within a repository in inbox rows.** Each directory is looked up once per inbox process, off the UI thread, with the root label as fallback.

# 0.79.1 (2026-10-07)

#### Fixed

- **The inbox no longer crashes on exit when a queued row highlight arrives after its tables have been removed.**

# 0.79.0 (2026-10-07)

#### Added

- **Inbox rows show a single PR number beside the session name.** An optional per-root `open_prs` hook supplies branch-to-number pairs, with an exactly-one-row brief table as fallback. PR URLs from either source make the number a terminal hyperlink.

# 0.78.0 (2026-10-07)

#### Added

- **`place toss <name>` can close a tmux session without a managed place.** It shows that no directory work was inspected before confirmation, and releases no directory.

# 0.77.0 (2026-10-07)

#### Changed

- **Reviewer lemons stay out of the default inbox.** Switching to one, selecting or pinning its row, or giving its brief a specially ranked status brings it into view.

# 0.76.0 (2026-10-07)

#### Added

- **Search the inbox and archive as you type with `/`.** Inbox matches retain their row formatting and fill the list first; when room remains, archive matches appear below a clear divider. The footer gives separate counts. Results match session and attached brief names, message, channel, directory, and branch.

# 0.75.0 (2026-10-07)

#### Added

- **`[tui] project_name_colors = true` gives project labels stable colors** in both inbox layouts, using the tmux window-label palette and directory overrides. It is off by default.
- **A mid-turn card keeps its brief status color beside the `working` headline.** A `blocked` status stays yellow while the session works on its answer, whether the age is on its own line or inline in the context row.
- **Project colors make timing labels neutral.** Independently, the selected row uses a deeper blue on dark themes; set `[tui] active_row_color` to override it at startup. Light-theme selection is unchanged by default.

# 0.74.4 (2026-10-06)

#### Fixed

- **A live session is no longer archived because another channel appeared on the same TTY.** Hooks record each tmux session identity, and the watcher compares that identity with the pane currently using the TTY. It keeps rows when the identity is missing or ambiguous instead of assuming the newest row replaced the older one.

# 0.74.3 (2026-10-06)

#### Changed

- **Resuming a detached tmux row reuses its recorded session when the identity still matches, or the only session at its recorded directory.** Lemonaid opens a new window there. If it cannot identify one safe destination, it shows a copyable resume command so you can choose the session yourself. Live rows keep their existing activation behavior, and detached rows retain the explicit `R` action.

# 0.74.2 (2026-10-06)

#### Changed

- **Rows kept after their terminal pane closes show a `detached` marker.** Live rows keep their existing activation behavior; Enter on a detached row explains whether `R` can resume it. The marker says when the backend or saved details cannot resume it, and `b` / `Tab` still opens the brief.

# 0.74.1 (2026-10-06)

#### Fixed

- **Codex sessions running under Node are no longer archived as exited. If a terminal pane closes while its attached brief is waiting on a person (`merge`, `approve`, `blocked`, or `alert`), its inbox row stays visible so you can open and answer the brief. Press `R` on a detached row to resume the session in tmux or cmux, using its recorded directory; WezTerm can switch to an existing pane but cannot recreate one.** History shows each archived session's attached brief status, and archive logs record the channel and reason.

### 0.74.20261006

#### Fixed

- **`place toss` refuses to release a checkout that supplies the active editable lemonaid install.** Reinstall lemonaid non-editably before releasing that place.

# 0.74.0 (2026-10-06)

#### Added

- **A stopped harness can hand off in its terminal with one CLI command.** Press Ctrl-Z in Claude or Codex, then run `lemonaid brief handoff --to codex` or `--to claude` in the returned shell. Lemonaid refuses ambiguous TTY matches, resumes the outgoing harness to finish its brief, and starts the replacement in the same terminal. If the replacement exits before accepting, it resumes the old session. The maintainer reported successful live trials in both directions on 2026-10-06.
- **Codex can finish the handoff by printing the ready marker in its completed final reply** after editing the brief, as the CLI prompt permits.
- **Same-terminal handoff restores the shell's terminal settings on return and rollback.** PTY coverage checks a raw-mode target and a signal-aware mock TUI across Ctrl-Z and resume.

# 0.73.0 (2026-10-06)

#### Added

- **Keep your own notes in view under the sessions.** Set `[tui] notes` to a Markdown file, and the sidebar shows it under the cards: key hints while you learn tmux, a checklist, anything you want in sight. The notes take up to 40% of the space under the title bar and scroll past that; the cards size themselves to the rest. An edit to the file shows on the next refresh. `N` hides the notes and shows them again. A top strip never shows them.

# 0.72.0 (2026-10-06)

#### Added

- **The brief view identifies the brief and its lemons.** Under the session line come the brief's title, its `Brief-ID:`, and `Parent:` with the parent's session name when lemonaid knows it. The name after the dot is bold; the description is dimmed. Children and `brief show` use the same emphasis. Recent update times use the inbox's green; times over a day old use its gray.
- **`[tui] brief_names_in_inbox = true` shows each attached brief's name after its session name,** in both the column layout and the sidebar. Off by default.

# 0.71.2 (2026-10-05)

#### Added

- **Press `Y` in either brief view to answer the selected question with `Yes, approved`.** The answer is sent immediately with the usual reminder to update the brief's Status. Set `answer_yes` under `[tui.keybindings]` to change the key; `a` still opens the free-text answer box.

# 0.71.1 (2026-10-05)

#### Fixed

- **lemonaid's own text colours stay readable on a light Textual theme.** What a lemon needs from you, the unread dot, a running process, a brief's status word and its links and quoted needs were pale colours chosen for a dark background, about 2:1 against white. Under a light theme they take darker versions, each at 4.5:1 or better; a dark theme looks as before. Filled headlines and bars keep their colours, which read on either.

# 0.71.0 (2026-10-05)

#### Added

- **Harness handoff replaces the outgoing harness in its tmux pane.** After readiness, tmux starts the target in the same pane and keeps that pane available for rollback. If the target exits or acceptance times out, lemonaid resumes the old session there. Without tmux, readiness prints a command to run in the same terminal after the old harness exits. The new harness accepts with its own session ID and token; brief ownership and manual inbox state transfer after its notification appears.

# 0.70.2 (2026-10-05)

#### Fixed

- **Claude session names set with `/name` are found in `~/.claude/history.jsonl`.** The older `/rename` command still works.

# 0.70.1 (2026-10-05)

#### Fixed

- **`brief show` displays matched Questions entries by default and flags unmatched headings.** Use `--no-questions` for compact text output; `brief check` also reports headings with no matching Needs bullet. Existing mismatches do not block unrelated brief edits.

# 0.70.0 (2026-10-05)

#### Added

- **Running Claude and Codex composers can use Ctrl+Enter for lemonaid submissions.** Set `submit_key = "C-Enter"` under each harness's `[backends.<name>]` after configuring its own submit binding. Shell command entry still uses Enter.

# 0.69.1 (2026-10-05)

#### Fixed

- **Claude can finish a harness handoff with the token marker in its final reply.** A changed, stable, valid `## Handoff` still has to be present. The request asks for at most five bullets and no file reread when the brief is current. The outgoing Claude's Stop hook also permits its waiter to remain stopped during a pending handoff while continuing to check the brief. On timeout or coordination failure, the checked source pane is prompted to rearm its waiter.
- **Handoffs preserve an active snooze and a meaningful session title.** The outgoing turn no longer clears its pending snooze, and a real outgoing title carries across until the new harness has its own title. An expired or removed snooze stays cleared.
- **Concurrent handoff checks launch only one replacement window.** Foreground status calls and the background coordinator serialize each token's advance before opening its target pane.
- **Codex launches work from directories with Unicode names.** The trust-path argument keeps the directory's real characters instead of shell-invalid surrogate escapes.

# 0.69.0 (2026-10-05)

#### Added

- **`lemonaid brief handoff --to claude|codex` moves a brief between tmux harness sessions.** The outgoing lemon writes a tokened `## Handoff`; the new lemon acknowledges it before the brief, manual name, emoji, pin and active snooze move. Each backend keeps its own session ID and transcript, and resuming the old session reclaims the brief.
- **Tokened user messages can finish either acknowledgement.** `brief handoff status <token>` reports the phase and exact phrases; `ready` and `accept` CLI verbs provide a fallback.

# 0.68.1 (2026-10-05)

#### Fixed

- **A Claude session is named by Claude's title even after it changes directory, or when its project path has an underscore.** The title is read from the transcript Claude reports to the hook, rather than from a folder guessed from the session's current directory, and that guess now encodes every character but a letter or digit as `-`, as Claude does. Before, such a session showed its current directory's name. The transcript watcher and `summarize` use the corrected folder name too.

# 0.68.0 (2026-10-03)

#### Added

- **A bare `--codex-thread` on `lemonaid watch doc|pr|file` queues into the lemon's own thread** (`$CODEX_THREAD_ID`). With the variable written into the command, Codex's `lemonaid watch` allow rule doesn't match and the automatic approval reviewer can refuse the waiter; the bare form matches. The watch skills and the review brief template now use it.

# 0.67.0 (2026-10-03)

#### Changed

- **`lemonaid place toss` closes only the windows in a shared session.** The session and its other windows stay; a dedicated session still closes whole. The plan is made again after the confirmation prompt, and any change in tmux since stops the toss.
- **A bare `lemonaid place toss` never falls back to the caller's own session.** A directory that isn't a listed place refuses, and closing the session the command runs in unattended (`--json` or `--yes`) needs its key.

# 0.66.0 (2026-10-03)

#### Added

- **An `approve` brief status**, for a reviewer lemon that recommends approving a teammate's PR when only your Approve on GitHub is left. It sorts directly below `merge`, fills purple, and gets the same Status reminders as `blocked`, `alert` and `merge`.

# 0.65.1 (2026-10-03)

#### Fixed

- **`lma` refreshes installed skills after an upgrade.** At startup it re-renders the skills `lemonaid skills install` put in place when the packaged text has changed, and says so in one line; the install docs now say to run `skills install` after installing or upgrading.

# 0.65.0 (2026-10-03)

#### Changed

- **`lemonaid place toss` works on one place, not the caller's whole session.** The session closes with it only when dedicated to that place; a shared session is refused, naming the windows in the place.

# 0.64.2 (2026-10-03)

#### Fixed

- **`lemonaid watch pr --head` accepts an abbreviated SHA** instead of reporting the head moved at once. It refuses anything but 7 to 40 hex digits, since a shorter prefix could also match a later push.

# 0.64.1 (2026-10-03)

#### Fixed

- **`lemonaid watch doc` waits for a doc that doesn't exist yet** instead of failing at startup, and reports `<doc> was created` once the doc is written. A watch list does the same for its entries.

# 0.64.0 (2026-10-03)

#### Added

- **`lemonaid restore tmux` brings lemons back working, not just their windows.** A resumed Claude or Codex lemon whose brief lists waiters starts on a prompt to rearm them. Restore then waits and reports which lemons are working and which are stuck, exited, or need rearming by hand, with each pane's last lines. `lemonaid tmux restore` is the same command.
- **`lemonaid claude resume <id>` takes an optional first prompt** for the resumed session.

# 0.63.2 (2026-10-02)

#### Fixed

- **Brief verbs no longer drop a child brief's `Parent:` and `Area:` lines.** A verb that created `## Now` put it above those lines and then overwrote them. `brief check` now reports a missing `Parent:` line when lemonaid records a parent for the brief.

# 0.63.1 (2026-10-02)

#### Fixed

- **`lemonaid tmux restore` brings sessions back in the order tmux made them, not by name.** Sessions recorded before this release come back after the others, by name.

# 0.63.0 (2026-10-02)

#### Added

- **Selecting a session in `lma` switches to its cmux workspace and surface.** It works with no setup; see [docs/cmux.md](docs/cmux.md). There is no back navigation yet.
- **A cmux session that has lost its surface is found again or resumed.** After a cmux restart, lemonaid switches to the surface cmux moved it to, and otherwise resumes it in a new workspace in its directory.

# 0.62.1 (2026-10-02)

#### Fixed

- **`--self` works inside the Codex sandbox, where tmux can't be asked.** `brief` verbs, `inbox rename` and `inbox emoji` take the caller from `LEMONAID_CHANNEL`, `CLAUDE_CODE_SESSION_ID` or `CODEX_THREAD_ID` before its tmux pane, as `tell` does. A bare `brief show` outside tmux shows the caller's own brief.

# 0.62.0 (2026-10-02)

#### Added

- **`lemonaid brief waiter add|set|rm` keeps a brief's `## Waiters` current without a hand edit.** `set` and `rm` name a waiter by part of its command, and `set <match> --head <sha>` rearms a `watch pr` waiter on a new head.

# 0.61.1 (2026-10-02)

#### Changed

- **`watch pr --comments` skips only comments signed with `--me` or a `--legacy` signature.** A comment is yours when it starts `🍋 <signature>:`, e.g. `🍋 Author (MotorHoe): done`. Other lemons' 🍋 comments, signed or not, now wake the waiter, so its first wake after upgrading reports the PR's unresolved unsigned ones once.

# 0.61.0 (2026-10-02)

#### Added

- **Snooze presets are configurable, and durations take `w` for weeks.** `[inbox] snooze_presets` lists what the picker offers, by default 30m, 3h, 1d and 4d, each labelled from its duration (`Tomorrow morning, Sat 09:00`).
- **`[inbox] snooze_day_starts` (09:00) sets when day snoozes end.** It is separate from `day_starts`.

#### Changed

- **A snooze in days or weeks counts mornings.** `Nd` ends at the Nth `snooze_day_starts` after now, so `1d` at 02:00 wakes at 09:00 that day. `1.5d` counts two mornings, and `morning` is `1d`. The TUI and `inbox snooze` share it.

# 0.60.0 (2026-10-02)

#### Added

- **`lemonaid brief children --self` shows a parent its children and what holds up their cleanup.** Each child shows its Status and how long it has held it, its place and whether the directory still exists, its tmux session and attached clients, its `### PRs`, and its reviewers nested under it. `cleanup` reads `ready`, `held` (with the reasons), `orphan` (not done, session gone) or `cleaned`. Whether the branch is merged is still the parent's to check.

# 0.59.0 (2026-10-02)

#### Added

- **A `waiting` card shows how long it has been waiting** (`waiting 3 days`) in place of its brief's age. lemonaid records when it first sees a brief's `Status:` change, so edits to `## Now` don't reset the count. Arrangers get it as the brief's `since`.
- **`card_fields` takes `age`,** which puts the brief's age on a card's second line instead of a line of its own.

#### Changed

- **The snooze picker takes a typed duration as soon as it opens** (`45m`, `2h`, `3d`, `morning`), with no trip through Custom. With the box empty, Enter takes the highlighted preset, and Up and Down move the highlight.

# 0.58.3 (2026-10-02)

#### Changed

- **`lemonaid inbox arrange serve` loads its file again whenever it changes,** so an edit to an arranger takes effect at the next snapshot without restarting `lma`. A file that fails to load is answered as an error, which `lma` shows while it keeps its own order.

# 0.58.2 (2026-10-02)

#### Changed

- **With `fold_statuses`, the lemon in the tmux pane you're looking at stays out of the fold.** Click into a `waiting` lemon's pane and its card shows in the list; it folds back on the next refresh after focus moves on, unless the cursor is on it, in which case it stays until the cursor leaves.
- **Focusing the pane of a lemon the inbox had archived brings it back, as read,** when its harness is still running there and no newer session holds that tty. Long-lived lemons archived by mistake no longer stay hidden in history.

# 0.58.1 (2026-10-02)

#### Fixed

- **A card too narrow for the time and the project drops the time,** rather than cutting the project's name.
- **A card outside every root, with `project` and `cwd` both in `card_fields`, shows the cwd fallback in the project's place,** not wherever `cwd` comes in the list.

# 0.58.0 (2026-10-01)

#### Changed

- **An inbox card's second line shows the lemon's project instead of its cwd:** `time · project[: area] · branch`. The project comes from `[[places.roots]]` and the brief's `Area:` line. A session under no root and on no branch still shows its cwd. A narrow card cuts the branch first, then the area. The column layout's `CWD` column becomes `Project`.

#### Added

- **`[tui] card_fields`** picks what that line shows, and in what order, from `time`, `project`, `branch` and `cwd`.

# 0.57.0 (2026-10-01)

#### Added

- **`[inbox] arrange` names a program that decides the order of `lma`'s list and what folds at its bottom.** `lma` keeps it running and sends it a JSON line of the inbox's rows whenever they change. While it fails, `lma` draws its own order and says why in the status line. See [docs/arrange.md](docs/arrange.md).
- **`lemonaid inbox arrange check` tries an arranger against the live inbox** and reports what it got wrong. `arrange snapshot` prints what an arranger is sent, and `arrange serve FILE` runs a Python file's `arrange(snapshot)` as one.

#### Fixed

- **`u` (jump to unread) lands on the unread session when a folded group sits above it in lemonaid's order,** as `done` sessions do with `fold_statuses = ["done"]`.

# 0.56.2 (2026-10-01)

#### Changed

- **With `mid_turn_working`, a mid-turn lemon's brief view keeps its `Needs` block and questions.** They are dimmed while the turn runs, and `a` still answers them. The inbox card is unchanged: no fill and no `Needs` line until the turn ends.

# 0.56.1 (2026-10-01)

#### Changed

- **With `mid_turn_working`, a mid-turn lemon keeps its place in the list.** A `blocked` lemon at work on your answer stays in the `blocked` band instead of dropping to the bottom, and folds by its brief's status. Its card is drawn as `working`, with the brief's status in dim text before its age (`blocked · updated 3m`).

# 0.56.0 (2026-10-01)

#### Changed

- **A brief card leads with the lemon's project, then its name, then its branch,** so you can tell which repo a brief is about at a glance. The project is the `[[places.roots]]` entry the session sits under, named by its new `name` setting or its directory, and the session's own directory outside every root. The branch now comes before the directory on the card's second line, so a narrow pane cuts the directory first. `brief show` puts the project first in each lemon's heading too.

#### Added

- **A brief's `Area:` line names the part of the project the work is in, and the card shows it after the project:** `ds-monorepo: apps/unified-asset`. `brief new --child --area <path>` writes it. Without one, a lemon working below its session's directory shows that subdirectory instead.

# 0.55.0 (2026-10-01)

#### Added

- **`Ctrl`+`a` moves to the top of the inbox list and `Ctrl`+`e` to the bottom, in the wide table and the sidebar.** `Home` and `End` do the same. The bottom is the last row shown, so a folded group stays folded and the lower table of other terminals' sessions is skipped. Rebind them with `[tui.keybindings] first` and `last`.

# 0.54.1 (2026-10-01)

#### Fixed

- **The one-call Codex edit shown in the watch-doc skill and docs no longer records a failed patch as the lemon's own edit.** `--mine` now sits on the `apply_patch` line after `&&`, so it runs only when the patch succeeds. An `--editing` older than 10 minutes no longer pairs with a later `--mine`, so one left behind by a failed patch can't cover someone else's edit.

# 0.54.0 (2026-10-01)

#### Added

- **`lemonaid watch doc` no longer wakes a lemon for its own edits to the doc's body.** Claude Code records them with PreToolUse and PostToolUse hooks (`lemonaid claude hooks --own-edits`), and Codex, or an edit made through a shell, with `lemonaid watch doc --editing <doc>` before the edit and `--mine <doc>` after it. An edit by anyone else still wakes it, even one made earlier in the same turn.

# 0.53.0 (2026-10-01)

#### Added

- **`[tui] mid_turn_working = true` shows a lemon mid-turn as `working`, whatever its brief's `Status:` says.** It is off by default. Its card, sort position and brief view say `working`, without the `Needs` line or its question, until the turn ends, when the brief's status applies again; `running` is left alone. The watcher reads turn boundaries from each Claude and Codex transcript, and a turn silent for 20 minutes counts as over.

# 0.52.1 (2026-10-01)

#### Fixed

- **The tmux status-line commands and the Claude statusline start in about a third of the time (50-90 ms, from 140-185 ms).** They no longer import Textual or the inbox TUI, so the status bar fills in sooner after a session switch, and running them every second costs much less CPU.
- **In follow mode, the sidebar marks the session you switched to straight away.** It used to wait up to about a second and a third for its next check of which pane has focus.
- **An idle inbox no longer redraws its whole table three times a second.** Each refresh updates only the cells that changed.
- **A brief waiting for its lemon no longer costs the inbox a `tmux list-windows` on every refresh.** It looks for its window again only when a lemon starts, returns from the archive or records a new window, and every 30 seconds for changes only tmux knows about. A brief that has waited 15 days stops waiting.
- **The sidebar checks its size against the saved one without asking tmux.** That was another tmux call on every refresh.
- **The inbox no longer stalls for up to a fifth of a second while its watcher looks for Claude transcripts.** It used to read all of `~/.claude/history.jsonl` once per session it couldn't place, on every retry. It now keeps an index of the file and reads only the lines added since its last look.

# 0.52.0 (2026-10-01)

#### Added

- **A lemon is told the local time, weekday and date on its first turn of each day,** as one line: "It's 9:14am Thursday, 2026-10-01." A session that runs for days keeps the date it started with otherwise. A day starts at `[inbox] day_starts`, 06:00 by default, so a lemon working past midnight hears it in the morning. Claude gets it from the `lemonaid claude submit` hook, which also runs when a background task wakes the session, and a Codex thread at the end of its first queued message of the day.

# 0.51.0 (2026-10-01)

#### Added

- **A lemon whose brief is `blocked`, `alert` or `merge` is reminded what it waits on, so it updates Status once an answer moves the work on.** An answer sent from the brief view ends with the `Needs` labels it leaves, and a message queued into a Codex thread ends with all of them.
- **`lemonaid claude hooks --status-note` installs a PostToolUse hook that gives a Claude lemon the same reminder** on the first tool call of each turn, as added context. It never blocks or starts a turn, and a later tool call in the turn exits in the shell, without starting Python.

# 0.50.1 (2026-10-01)

#### Changed

- **`running` sessions sort just below `blocked` and above `merge`, read or unread.** Before, a read `running` row sat below every unread session, and an unread one mixed in with the other unreads.

# 0.50.0 (2026-10-01)

#### Added

- **`lemonaid brief bullet add|set|rm` and `brief pr add|rm` edit one line of `## Now`.** They keep the sub-headings in the rules' order, with a blank line around each, and drop a heading or PR table left empty. `set` and `rm` name a bullet by the start of its text and fail unless exactly one matches.
- **`lemonaid brief check` reports what is wrong with a brief, and exits 1 if anything is.** It looks at the title, `Status:`, `Lemon-ID` (against the database), the order and contents of `## Now`'s sub-headings, the PR table, and whether `## Waiters` is last. Every edit verb, `brief now` and `brief status` included, refuses an edit whose result fails it, and `brief now` lays out its section the same way, and the Claude Stop hook blocks a turn's end while the brief fails it. `--all` checks every brief of a session that isn't archived.
- **`[brief] pr_url` lets `brief pr add` take a PR number instead of its URL.**

# 0.49.0 (2026-10-01)

#### Added

- **Answer a lemon's question from its brief.** A brief view shows each `## Questions` entry under the `Needs` bullet it explains, matched on the bullet's label (its text before a colon, or all of it). `[` and `]` select a question, `a` sends a one-line answer to the lemon's inbox and `d` asks it for more detail, both as `lemonaid tell` would. The four keys are `[tui.keybindings]` entries.
- **`lemonaid brief show --questions`** prints those entries under their bullets; without it, `## Questions` is left out.
- **The config warns when one key is bound to two actions** in the inbox list or the brief view, the `up_down` keys included.

#### Changed

- **The `b` popup is the sidebar's brief view, not `less`.** It takes the same keys and still closes on `q`, Escape and the tmux key that opened it.

# 0.48.0 (2026-10-01)

#### Added

- **`lemonaid brief new --child "<title>"` writes a brief for a lemon that hasn't started yet.** It fills `Lemon-ID:`, `Status: working` and `Parent:` from the caller, attaches it to no one, and prints the path for `--brief`. `--template review --pr <url> --review-doc <path>` writes a reviewer's brief with its waiters, and `~/.lemons/brief-templates/<name>.md` replaces or adds a template.

# 0.47.0 (2026-10-01)

#### Added

- **`[tmux-session.templates]` names templates after their harness, and `default` can name one: `default = "claude"`.** `--harness claude` and `--harness codex` then pick a lemon by name, and a list-valued `default` still works. A `default` naming a missing template, or itself, is reported when the config loads.

# 0.46.0 (2026-09-30)

#### Added

- **`lemonaid inbox snooze --self 2h` lets a lemon snooze its own inbox row.** It takes the TUI picker's syntax (`45m`, `2h`, `3d`, `morning`) and the targets of `inbox rename`, and `--clear` wakes the row. Unlike a TUI snooze, it lasts through the lemon's turn ends, including the one it was set in, and wakes unread if any of them ended unread; a permission prompt or a question still wakes it at once.
- **`inbox rename`, `inbox emoji` and `inbox snooze` take `--lemon <Lemon-ID or brief name>`.**

# 0.45.1 (2026-09-30)

#### Fixed

- **`scripts/demo-screenshot.py` draws the inbox in your terminal's colors.** It takes the 16 ANSI colors, bold handling and minimum contrast from `scripts/demo-palette.json` (`--palette` for another), which `scripts/terminal_palette.py` extracts from an iTerm2 profile, and it draws faint text. `scripts/demo-inbox.py` takes `transparent` from your lemonaid config, so the demo inbox uses the ANSI colors when yours does.

# 0.45.0 (2026-09-30)

#### Added

- **A `running` brief status: the lemon is minding a pipeline run or another long process.** `lemonaid brief status` accepts it, and the inbox fills its card and top-strip row teal, shows the first line of `## Now`'s `Running` part on its card, and sorts a read one just above the other read sessions.

# 0.44.0 (2026-09-30)

#### Added

- **`lemonaid brief id --reroll` gives a lemon a new WordyBin; `--set QuickOdd` picks it.** The brief line, inbox (pending and `done/`), and parent links move to the new ID. The old ID stays an alias, and its inbox folder forwards, so a message sent to it by a lemon that cached it still arrives.

# 0.43.2 (2026-09-30)

#### Fixed

- **A brief waiting on a window reaches a lemon that was already running there before the inbox placed it.** `brief attach --session S:W` right after a `codex --no-daemon` started recorded the Codex as live before the brief, so it could never claim it. A Codex on the shared app-server is still refused, since it is never placed, and so is a window already running more than one lemon.
- **A waiting brief that is then attached by channel stops waiting.** Its leftover row no longer shows in `brief list` as waiting for the window.
- **`lemon start` recognizes Claude's current folder-trust prompt.** It reads "Is this a project you created or one you trust?" and opens on "No, exit", so lemonaid reports it rather than answering.

# 0.43.1 (2026-09-30)

#### Fixed

- **`place open --prompt` starts the lemon whatever the prompt contains and whatever your shell is.** The prompt used to be typed into the harness window POSIX-quoted, which xonsh rejects, so a prompt with an apostrophe never started its lemon. It now reaches the harness through the window's environment as `"$LEMONAID_PROMPT"`, and `lemon start` does the same.
- **`place open --brief` attaches the brief to the session it just opened.** It used to find that session again by its directory, and lemonaid's scratch pane, in whichever session you're looking at, often reports the same directory, so the lookup failed as ambiguous with "could not tell which session". `--json` now also reports the `session`.
- **`place open --prompt` reports a new lemon stuck at a startup dialog**, such as Claude's folder-trust prompt, instead of reporting success. `--no-check` skips the check.

# 0.43.0 (2026-09-30)

#### Added

- **`lemonaid lemon start SESSION:WINDOW` starts a lemon in another window of a session from config.** It runs a `[tmux-session.templates]` harness line, as `place open` does for its harness window, and takes `--prompt`, `--brief`, `--parent` and `--name`. It makes the window or respawns a dead one, and refuses a window with anything running in it. With `--brief`, a Codex template line needs `--no-daemon`, as it does for `place open --brief`, since a Codex on the shared app-server can't be matched to its window.
- **`place open --name` names the brief's lemon's session once it starts.**

#### Fixed

- **Codex started from a template no longer stops at its folder-trust or update prompt.** lemonaid passes `-c` overrides for both, so a prompt given at launch reaches it.
- **`brief attach --session S:W` fails, rather than waiting forever, when a lemon already runs in that window with no inbox row placing it there.** A Codex on the shared app-server records no tmux location, so the brief used to wait for a new lemon that never came. The error lists that directory's unplaced Codex sessions as candidates for `--channel`.

# 0.42.1 (2026-09-30)

#### Fixed

- **`place toss` no longer detaches a client watching the session it kills.** It switched a client away only when the caller's own pane was in that session, so a lemon tossing a place by key from elsewhere detached anyone looking at it. Every attached client now goes back to its last session (or the usual fallback) first, and `toss` refuses if one has nowhere to go or tmux can't say who is attached.
- **`place toss` from inside a session nobody is watching leaves other clients alone.** It used to run an untargeted `switch-client`, which tmux could apply to a client in some other session.

# 0.42.0 (2026-09-30)

#### Changed

- **The Obsidian vaults that brief links open come from `[brief] vaults`, and none are configured by default.** It lists vault directories; a bare `.md` path under one, from `~` or in full, opens that note in the vault named after the directory. With none listed, such paths stay plain text.

# 0.41.1 (2026-09-30)

#### Fixed

- **The scratch toggle acts on the session whose key ran it.** A `run-shell` binding has no pane of its own, so lemonaid asked tmux for "the current window", and tmux answered with whichever session was active most recently. A session another process created or attached in that moment took the scratch pane out of your window. lemonaid now names the session from `$TMUX`.
- **`LEMONAID_LOG` moves the shared log** away from `/tmp/lemonaid.log`.

# 0.41.0 (2026-09-30)

#### Added

- **A `review` brief status: the next move is a teammate's approving review, not yours.** `lemonaid brief status` accepts it, and the inbox fills its card and top-strip row brown, shows its `Needs` line as for `blocked`, and sorts it below `merge` and above `done`.

# 0.40.1 (2026-09-30)

#### Fixed

- **`brief show <session> --popup` from a key binding shows the lemon in the window you pressed it from.** A binding that passes only `#{session_name}` showed every lemon in the session, so a lemon with no brief looked like it had its neighbour's `Status:`. A named window, and callers outside that session, still get what they asked for.

# 0.40.0 (2026-09-30)

#### Added

- **Tab opens the brief, like `b`.** It shows the highlighted row's brief, or returns to the inbox from one. The new `[tui.keybindings] brief_key` names the key (`"tab"` by default, `""` to unbind), since `brief` takes only single characters.

# 0.39.0 (2026-09-30)

#### Added

- **`lemonaid skills install` installs packaged `watch-doc` and `watch-pr` skills for Claude Code and Codex.** It links each harness's skills directory to one copy lemonaid renders, and never replaces an entry it didn't create. `--print <name>` gives the text instead. See `docs/skills.md`.
- **Your own additions to a skill go in `~/.lemons/skills/<name>/overlay.md`**, which install appends after the packaged text (a `SKILL.md` there replaces it instead). Install renders when it runs, so after adding or editing an overlay, or upgrading lemonaid, run it again; it rewrites the rendered copy and the links stay put.
- **`lemonaid watch pr --comments` wakes the author when the PR conflicts with its base or its CI fails.** Each is reported once per head commit, so a rearm on the same head stays quiet. CI counts only required checks when the PR has any, and waits until every check on the head has finished.

#### Changed

- **`lemonaid watch doc` reports body edits by default, after 20 seconds of quiet.** Editing a watched doc now wakes its lemon without a comment. `--no-edits` restores comments-only, and `--quiet` still sets the delay (it was 45 seconds).

# 0.38.0 (2026-09-30)

#### Added

- **`[tui] fold_statuses` folds sessions of those brief statuses into one line at the bottom of the inbox.** With `["waiting"]`, read `waiting` sessions collapse into `▸ waiting (N)`, and `w` shows or hides them. Pinned and unread sessions stay in the list. Empty by default, so nothing folds until you set it.

# 0.37.0 (2026-09-30)

#### Added

- **`[inbox] auto_read` leaves a session read when its turn ends with a matching final message.** Patterns are regexes matched from the start of the final assistant message, for Claude, Codex, OpenCode and OpenClaw. None are configured by default, and `lemonaid for-lemons` lists the configured ones.

# 0.36.5 (2026-09-30)

#### Changed

- **A brief's children are listed one per line, after the rest of `## Now` and before `Done`.** Each line shows the child's brief status, coloured as on its card, then its session's name, or its Lemon-ID's slug when it has no session. The pager now shows `Parent:` and `Children:` too.

# 0.36.4 (2026-09-30)

#### Fixed

- **Selecting a live Codex row switches to its pane.** Rows with no tty were matched by pane title, which names neither Codex nor Claude, so a running Codex read as gone. The lookup now checks for the harness process on each pane's tty, matching the executable's name rather than any path that contains it. Two matching panes, or a pane `ps` can't read, stop the switch rather than guess.
- **Recreating a dead session resumes that session.** It started the template's harness as-is, so a Codex row got a fresh Claude. It now runs the backend's resume command, and refuses a row it cannot resume or whose name another tmux session holds.

# 0.36.3 (2026-09-30)

#### Fixed

- **The watch-doc turn sent to an OpenClaw worker refers to "the user"** instead of naming the maintainer.

# 0.36.2 (2026-09-30)

#### Fixed

- **The inbox watcher backs off rows whose transcript never appears.** It retried each one every 5 s forever, and a Claude miss parses all of `~/.claude/history.jsonl`; a few dozen such rows kept the sidebar near a quarter of a core. Retries now double from 5 s up to 2 minutes, and start over when the row gets a new notification.

# 0.36.1 (2026-09-29)

#### Fixed

- **The scratch sidebar no longer goes blank when another session changes window.** A window created or selected in a session no client was showing pulled the pane there, leaving an empty placeholder in the window on screen until `prefix+l`.

# 0.36.0 (2026-09-29)

#### Added

- **`merge` and `alert` brief statuses.** `lemonaid brief status` accepts both, and the inbox reads them from any brief. `merge` (green) means only your merge is left; `alert` (red) means your move is urgent because harm grows while it waits.
- **The inbox sorts `alert` above `blocked` above `merge`**, all below the pins and above `done`. Cards, top-strip rows, and the brief popup and sidebar fill `alert` red and `merge` green.

# 0.35.0 (2026-09-29)

#### Added

- **Parent links between lemons, by Lemon-ID.** `lemonaid lemon parent` shows, sets or clears a lemon's parent, and `lemonaid lemon children` lists its children with their brief's `Status:` and channel. A link that would make a lemon its own ancestor is refused.
- **`place open --brief F --parent self` records the parent when it opens the place**, before the child starts.
- **The brief view shows a brief's parent and its children's status** under its card, in the sidebar, popup and `brief show`.
- **`lemonaid tell --parent` and `tell --child <lemon>` follow those links.** A child whose lemon hasn't started yet gets the message in its inbox.
- **Briefs and inboxes move to `~/.lemons/brief/` and `~/.lemons/inbox/`, with `lemonaid home migrate`.** Lemonaid keeps using `~/.brief-lemons/` until the migration finishes. The migration copies and verifies every file, rewrites the database's brief paths, and keeps the old home as a backup, refusing while any inbox waiter is running. See `docs/home.md`.

#### Fixed

- **A pending brief reaches a lemon resumed from the archive into its window.** It used to wait only for inbox rows newer than the request, and a resumed session keeps its old row.
- **`brief attach --session S:NAME` finds a window by its tmux name, and follows it if tmux renumbers it.** A name tmux doesn't know is an error; before, a name was accepted and never matched.

# 0.34.3 (2026-09-29)

#### Fixed

- **A link in a brief's heading opens in its own app from the sidebar**, and is a terminal hyperlink, like links in paragraphs and tables.

# 0.34.2 (2026-09-29)

#### Fixed

- **A Codex session run by the shared `codex app-server` daemon no longer borrows another session's pane.** The daemon keeps the tty of the TUI that started it, so every Codex session recorded that one tty, and the watcher archived live ones as older sessions on it. Their notifications now record no tty.
- **The watcher archives a Codex row with no tty once no Codex process other than the daemon is working in its directory**, so killing its session removes it from the inbox. Two Codex sessions sharing a directory keep each other's rows; `codex --no-daemon` avoids all of this (see `docs/codex.md`).
- **`lemonaid place toss` archives the rows on the killed session's panes and in the directories it releases**, whether or not the watcher could place them. Codex rows are matched by directory only, since an older one may carry another pane's tty.

#### Changed

- **Selecting a row whose pane and directory are both gone offers to archive it**: `a` in the error pop-up archives, with the usual undo.

# 0.34.1 (2026-09-29)

#### Fixed

- **A link in a brief's table opens in its own app from the sidebar.** A click on a table cell's `obsidian://` review-doc link went to the browser with its file path decoded, and cmd-click had no terminal hyperlink to follow.

# 0.34.0 (2026-09-29)

#### Added

- **`lemonaid watch doc` waits for Relay Comments on a document and wakes the lemon that wrote it**, by exiting (Claude background task), queueing into a Codex thread, or running an OpenClaw agent turn. It takes the standalone `watch-doc.py`'s flags and shares its state and locks, so the two can run side by side. See `docs/watch.md`.
- **`lemonaid watch pr` waits for a push, merge, draft or review-decision change, or new human comment on a GitHub PR.** It takes the standalone `watch-pr.py`'s flags and shares its state and locks.
- **`lemonaid watch file` waits for files or directories to change** and wakes the lemon the same way. A rearmed waiter reports what changed while none ran.
- **`lemonaid watch openclaw start|stop|list`** manages one watch list and one waiter unit per OpenClaw session, sharing lists with `openclaw_watch.py`.

# 0.33.0 (2026-09-29)

#### Changed

- **The tmux scratch pane starts as a left sidebar.** `scratch_position` in `[tmux-session]` now defaults to `left`; a configured `top`, or a position already saved with `--flip`, `--position` or `f`, still wins.
- **`[tui] brief_status` colours the top strip's rows too.** A `blocked` row fills amber and a `done` row blue, like their cards' headlines, and a read `waiting` row dims. The current session's green bar stays, and on a coloured row or headline the model is a badge in its provider colour.
- **The sidebar no longer draws an empty coloured row above its cards.** The top strip keeps its labelled header, including its unread and history colours.

# 0.32.1 (2026-09-28)

#### Fixed

- **Enter on a history session that is still running returns it to the inbox for good.** It comes back as the newest session on its tty, so the watcher's "keep the newest session per tty" rule no longer archives it again on the next tick.
- **Enter on a history session whose pane outlived its harness resumes it** instead of switching to the shell left in that pane. A session counts as running only when its harness process is still on its tty, the same check the watcher archives on.

#### Changed

- **A key that fails to act says why in a pop-up** instead of a toast that is easy to miss: a switch or resume with nowhere to go, a failed tmux resume, a brief that can't be shown, a failed Claude patch. Any key closes it.

# 0.32.0 (2026-09-28)

#### Changed

- **Opening a brief focuses the scratch pane.** Up/down navigation shows each lemon's brief as soon as the key is pressed, then switches the main pane to that lemon while retaining keyboard focus; `Escape` or `q` returns to the list.
- **The brief shows whether its inbox entry is unread**, and `m`, `M`, `r` and `z` mark it read, mark it unread, rename it, and undo without leaving the brief.
- **`prefix+l` keeps a brief open when it focuses the scratch pane.** The brief toggle, `Escape` and `q` still close it.
- **Clicking the already-selected row in a focused scratch pane keeps focus in the inbox.** Enter still switches to that lemon, and so does a click from another pane.
- **The scratch inbox title and bottom edge turn teal when its tmux pane will receive keys.** The colour is `[tui] focus_color`.
- **`lemonaid tmux scratch --restart` reinstalls the follow hooks**, so an upgrade's hook changes take effect with its TUI.

# 0.31.3 (2026-09-28)

#### Fixed

- **`done` sessions sort together, right below `blocked`, whether read or not.** Unread ones come first, and the rest of the unread sessions follow. Unread `done` sessions used to sort among the other unread ones, apart from the read ones.

# 0.31.2 (2026-09-28)

#### Fixed

- **Codex threads started within a minute of each other no longer share one inbox row.** A Codex channel is now `codex:<thread id>` instead of its first 8 characters, which UUIDv7 threads from the same minute share, so a thread no longer inherits another's brief, name, emoji, pin, or messages. Upgrading moves existing Codex rows, pins, emoji, and brief attachments to the full id recorded in each row.

# 0.31.1 (2026-09-28)

#### Fixed

- **Codex subagents and approval reviewers no longer archive the session that spawned them.** Their turn-complete notifications are ignored, because they share the parent's tty and the watcher kept only the newest session on it. Resolving a session by cwd also skips them.

# 0.31.0 (2026-09-28)

#### Added

- **Codex lemons get their messages without arming a waiter.** A delivery service queues each pending message into the recipient's Codex thread and moves it to `done/` only once `codex queue` succeeds, retrying failures. `tell` starts it, as does a Codex turn ending with mail pending; it runs detached, one at a time, and exits after two idle minutes. `lemonaid inbox deliver` runs it in the foreground.
- **An optional Stop hook keeps each Claude lemon's inbox waiter armed.** `lemonaid claude hooks --waiter-check` installs `lemonaid claude waiter-check`, which blocks a lemon with a brief from ending its turn while no `inbox watch --self` is running for it. A second watch for the same lemon now exits with an error.

# 0.30.0 (2026-09-25)

#### Changed

- **Blocked sessions sort right below the pins, even when read, and read `done` sessions sort above other read ones.** The rest keep the old order: unread above read, newest first. The inbox and the sidebar sort the same way.
- **`u` and mark-read find unread sessions wherever they sit in the list.** `u` jumps to the oldest one, and marking a row read moves to the next unread below it. Both used to count rows from the top, which missed once pins or status bands came first.

# 0.29.0 (2026-09-25)

#### Added

- **`inbox watch --self` inside Codex queues the message into its own thread without losing it.** When `CODEX_THREAD_ID` is the watched channel's thread, the watch runs `codex queue` and moves the message to `done/` only once that succeeds; a failed queue leaves it pending for the next watch. `--codex-thread <thread>` names the thread explicitly.

# 0.28.0 (2026-09-25)

#### Added

- **Lemons can send Markdown messages to each other's stable-ID inboxes.** Each new brief gets a `Lemon-ID` made from its slug and a short WordyBin suffix; existing hex and hand-made IDs remain valid. Other attached briefs receive one when used. `brief id` prints it. `lemonaid tell` accepts that ID, a channel, or an attached brief name. `lemonaid inbox next --self` handles one pending message, while `inbox watch --self` waits for one. Both print the message and move its file to `done/`.
- **Message commands resolve self from harness session IDs or the current tmux pane.** A send from a person's shell uses their username as the sender. Watches keep the ID across brief renames, stop when the brief changes channel, and accept a timeout; messages include a send time and can be read from stdin.

# 0.27.0 (2026-09-24)

#### Changed

- **Briefs put what a lemon needs from you first.** The popup, sidebar and cards pull `Needs` (`Needs Peter`, `Needs you`, ...) out of `## Now` into a highlighted block under the lemon's name and status, whatever order the worker wrote. `## Now` can use `### Needs Peter`-style sub-headings as well as `- Needs Peter:` bullets, and `Done` always comes last.

- **A session with several lemons opens with its name as a bar, then one section for every lemon recorded in it.** A lemon without an attached brief uses the one in `.z/` named for it (or an unclaimed `brief.md`), and otherwise says it has none. The lowest window's lemon shows its whole `## Now`; the others show `Needs` and one line of `Waiting on`.

- **Briefs can show the live state of PRs they mention.** Set `[brief] pr_state` to a command that prints `open`, `draft`, `merged` or `closed` for `{ref}`, and each `PR #N` or pull-request URL gets that state beside the status, so a stale brief is visible. Unset, the number appears alone.

- **The brief popup and sidebar draw each lemon as its inbox card, opened up.** The name, model, working directory and branch use the card's colours, `blocked` and `done` fill the headline the same way, and status, age and PR states sit on the card's third line. What the worker wrote follows as Markdown, with `Needs` in the inbox's attention colour.

- **Paths and URLs in a brief open with cmd-click in the popup and sidebar, even when they wrap.** Bare `~/work/vault/...md` and `~/trove/...md` paths become Obsidian links, and bare `https://` and `obsidian://` URLs get short labels (`lemonaid#74`, a note's name). Each label is a terminal hyperlink on every line it wraps onto, drawn in its own sky blue. A click in the sidebar opens the link with the system opener (`open`, or `xdg-open` off macOS), so `obsidian://` links reach Obsidian rather than the browser. Existing Markdown links and code are left as written.

- **Cards show what a lemon needs from you right under its name and location**, with the label the worker wrote (`Needs Peter: ...`) in the attention colour, even on a dimmed waiting card. The brief age and what a waiting lemon is waiting on follow.

# 0.26.0 (2026-09-24)

#### Added

- **Briefs can stay visible in a left scratch sidebar while you type in the lemon pane.** `b` switches to the selected lemon and shows its brief there; `prefix+b` toggles the current lemon's brief. Switching windows or sessions, or pressing `prefix+l`, restores the inbox. The top scratch strip keeps using the popup.

# 0.25.1 (2026-09-24)

#### Changed

- **Brief popups show the lemon's session identity and the brief path above its status.** The header uses the recorded name, emoji, model, tmux location, working directory, and branch.

# 0.25.0 (2026-09-24)

#### Added

- **Cards can show an attached brief's status, age, and waiting reason.** Set `[tui] brief_status = true` to color blocked and done cards, dim waiting cards, and flag working or waiting briefs after `brief_stale_hours` hours. Unread remains a separate marker.

- **`lemonaid brief status` accepts `waiting` and takes only a state.** Notes go through `brief now`; older status lines with notes still supply their state.

# 0.24.3 (2026-09-24)

#### Fixed

- **`place toss` no longer leaves a dead reaper pane when tmux has `remain-on-exit on`.** The reaper removes its own session after teardown, and follow mode skips lemonaid's internal sessions.

# 0.24.2 (2026-09-24)

#### Fixed

- **Follow mode keeps at most one placeholder outside its parking session.** The last window left retains its layout for a quick switch back; older placeholders no longer accumulate across every window visited.

# 0.24.1 (2026-09-24)

#### Changed

- **Session emojis sit at the right end of a card's second line, next to its pin when present.** Card titles stay uninterrupted; single-line rows still show emojis before their names.

# 0.24.0 (2026-09-24)

#### Added

- **Briefs are attached to lemon sessions and live in `~/.brief-lemons/`.** `brief attach`, `new`, `now`, `status`, and `detach` take `--self`, `--session SESSION[:WINDOW]`, `--channel`, or `--id`, so a sandboxed lemon can keep its brief current and the control center can attach one on another lemon's behalf. `brief show`, `b`, and `prefix+b` show the attached brief first and fall back to `.z/` for older sessions.

- **`place open --brief <file>` attaches a brief to the first lemon that starts in the new session.**

- **`brief list --json` maps each brief file to its session.**

- **Only files inside `~/.brief-lemons/` can be attached or edited as briefs.** The write commands run outside Codex's sandbox, so the folder is their boundary.

# 0.23.0 (2026-09-24)

#### Added

- **A lemon can carry an emoji before its name.** `lemonaid inbox emoji --self 🦫` sets it for the calling harness session (its inbox channel), so it survives compaction and resume, and it shows on inbox rows and cards. An emoji another live session holds is refused; `lemonaid inbox emojis --json` lists the ones in use.

- **`lemonaid inbox rename --self "name"` sets the calling session's display name**, the same override as the TUI's rename key.

- **`--self` never guesses.** It picks the one live session recorded at the pane's tty, tmux session, and window, and otherwise errors and points to `--channel` or `--id`.

# 0.22.1 (2026-09-24)

#### Fixed

- **A brief is never read from above the session's place.** A place without its own `.z/` showed the nearest brief in any parent directory, such as the repo checkout's, which belonged to a different lemon. A lemon's working directory outside the place is not searched either. The search still climbs from a lemon's subdirectory to the place.

# 0.22.0 (2026-09-24)

#### Added

- **`b` shows the selected session's brief in a tmux popup.** It opens over your client, not the lemon's session, and starts at the brief's `Status:` line and `## Now` section; the task statement is below a rule. The reader view colours working yellow, done green, and blocked red; removes generic `Brief:` title prefixes; uses left-aligned headings; stays at 140 columns or less; and closes with `q` or `Escape`.

# 0.21.1 (2026-09-24)

#### Fixed

- **The inbox stays responsive when tmux is overloaded.** Focus checks query attached clients instead of every pane, and all background tmux queries have a short timeout.

- **The watcher no longer mistakes a failed pane listing for dead sessions.** An unavailable tmux server now leaves its sessions untouched until a later check succeeds.

- **tmux status helpers safely receive pane titles and paths containing shell syntax.** The documented formats use tmux's shell quoting instead of wrapping values in literal single quotes.

# 0.21.0 (2026-09-22)

#### Added

- **Session indicators show the model family when the transcript identifies it.** Anthropic models use muted orange `F`, `O`, `S`, or `H`; OpenAI models use soft-white `A`, `S`, `T`, or `L`. The backend letter or lobster remains while the model is unknown.

# 0.20.2 (2026-09-18)

#### Fixed

- **`lemonaid claude hooks` no longer replaces a symlinked `settings.json` with a plain file.** The settings file is written whole through a temp file and a rename, and a rename onto a symlink replaces the link itself. A `~/.claude/settings.json` that pointed into a dotfiles repo became a copy, and the dotfile it pointed at never got the hook. The write now follows the link and lands in the target, for `--uninstall` as well.

# 0.20.1 (2026-09-18)

#### Changed

- **The docs say which tmux you need.** tmux 3.0 or later for lemonaid, and 3.6 or later for follow mode. The follow hook uses the `#{!:...}` format operator, which tmux added in 3.6; on an older tmux that term expands to nothing, the hook's condition is never true, and the sidebar stays in the window it was in. Nothing in the code changed.

#### Fixed

- **The inbox no longer burns ~80% CPU at idle.** `db.connect()` ran schema init, migration discovery (a filesystem walk), and an exclusive lock on every call - roughly 50-70 times per second between the TUI refresh and the watcher thread. Now runs once per process. The watcher also ran `tmux list-panes -a` once per active session per tick; now one listing per server is shared between location recording and stale-session archiving.

# 0.20.0 (2026-08-26)

#### Added

- **A session can be pinned to a place in the list.** `p` pins the selected session or releases it; shift-up and shift-down move a pin one slot, and both keys are configurable. A pinned session holds its place whatever its status, so an unread pin no longer jumps to the top, and it is marked beside its backend label.

- **`?` opens a key reference.** It replaces the footer's one-row hint strip, which truncated in a sidebar and never showed the `?` it advertised. On a top bar it lays out in two columns, so a short pane does not scroll.

#### Fixed

- **Exiting your last shell ends the session again.** The placeholder left behind held the window open, and follow mode filled it with the inbox. Follow now kills the placeholder rather than the window, so tmux tears down the window and the session itself - where an attached client goes next is `detach-on-destroy`, which is yours to set.

- **The sidebar comes back on attach.** Reattaching changes no window and no session, so neither hook fired and the window kept a blank placeholder until `prefix+l`.

# 0.19.1 (2026-08-26)

#### Fixed

- **Marking a card no longer moves what is in it.** The bar was prepended to each line rather than placed in the column the card already spends on padding, so a card shifted right by one the moment it became the focused session. The unread dot moves into the cell the jump digit vacated, since the row you are already in is the one a number is no use on.

- **Two connections no longer run the same migration at once.** Every `connect()` migrates, and the TUI connects from its watcher thread while the main thread is doing the same - both read the same pending version and both applied it, the second failing on a column the first had already renamed.

# 0.19.0 (2026-08-26)

#### Added

- **The session you are sitting in is marked down its left edge**, in place of its jump digit. tmux is asked which pane is focused each refresh, so a switch made outside lemonaid moves the mark too.

#### Fixed

- **The selected row keeps each field's colour.** Textual gave the row cursor's foreground priority over each cell's own, so selecting a row repainted every field one colour - and colour is what tells the fields apart. Mouse hover is composed the same way and gets the same treatment.

- **Yesterday's rows say which day.** The clock-to-date switch was a 24-hour elapsed test, so 23:59 last night still read as a bare time by morning. Yesterday keeps its time behind a `y` marker; only older rows become dates. Under a day stays green, older goes grey.

# 0.18.1 (2026-08-25)

#### Fixed

- **A notification that cannot name its session is dropped rather than filed under a shared `unknown` channel.** Every backend collapsed a missing session id into one pseudo-session per backend, which then took the tty of whatever shell delivered it - so it appeared in the inbox sitting on a real pane, and the next such notification upserted over it. In practice every payload carries an id, so this only fires on a malformed call; dropping it with a logged warning is better than parking it on a pane in use.

# 0.18.0 (2026-08-25)

#### Added

- **Digits 1-9 then 0 switch to that session**, numbered from the top of the list. The number is the row's position and nothing else: it renumbers when the list reorders, so it is a shortcut for the row you can see rather than a name a session keeps.

  Only the first ten rows carry a digit; past that you scroll. A second digit would need a timeout to tell `1` from `12`, and that wait would be paid on every jump.

  The inbox only. In history Enter resumes rather than switches, and a resume is too costly to hang on one unconfirmed keystroke. The non-switchable table is unnumbered for the reverse reason: nothing there can be switched to at all. Set `jump_by_number = false` under the keybindings config to leave digits unbound.

#### Fixed

- **Read sessions are no longer bold.** The card headline styled the unread marker's slot whether or not there was a dot in it, and that style is bold. A colour change does not clear the bold attribute - only a reset does - so the bold from an empty marker carried forward into the session name, putting every row on the terminal's bold face regardless of its state.

- **The message is never bold**, on unread rows too. It is the one field that reads as prose rather than as a value to pick out, and a wrapped bold paragraph is harder to read than the plain one beside it.

- **Sessions whose transcript could not be found now get live messages.** The transcript directory was derived from the session's cwd, and Claude's own name for that directory does not always match - a session in `.../protostellar-visits/fast-visits-202609` was filed under `.../visits-202609`. The lookup missed, no message was ever written, and the row kept whatever generic text a hook last put there while the session was in fact talking. The path Claude reports in each hook payload is now recorded and used first, with a lookup by session id behind it.

- **A finished turn no longer replaces a session's last real message.** The transcript watcher writes what the session actually said, and only rewrites when the transcript changes - so a message the `Stop` hook overwrote stayed overwritten until the session spoke again. Whether you saw the real message or a generic one came down to which of the two wrote last, which is why it hit some sessions and not others. `Stop` now leaves existing message text alone; a permission prompt or a question still replaces it, since those are news the transcript does not carry.

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
