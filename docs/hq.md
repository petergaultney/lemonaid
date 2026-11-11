# Starting your HQ

An HQ is a lemon you keep pinned at the top of the inbox. It sees what every other lemon is doing, is told when one finishes or gets stuck, and can brief the lemons that are already running. Lemonaid has no special HQ role: it is an ordinary lemon with a brief, children, and a few waiters. This guide gets one running on a fresh install.

Commands here were checked against lemonaid 0.100. `lemonaid <command> --help` is the authority if they have drifted.

## 1. Prerequisites

Install lemonaid and make sure `lma` starts. See the [README](../README.md#installation).

### Claude hooks

The [notification hooks](claude.md#1-add-hooks-to-claude-settings) are the base. Then let lemonaid add its own:

```bash
lemonaid claude hooks --dry-run      # say what would change
lemonaid claude hooks --waiter-check --status-note --own-edits
```

- **No flag (SessionStart)** registers every Claude session, and where it runs, the moment it starts or is resumed. Without it a session nobody has spoken to yet is invisible, and that is the session a restore needs to find.
- **`--waiter-check`** adds a Stop hook that stops a lemon with a brief from ending its turn while no watcher runs for its brief: its push scout, or a `lemonaid watch --self` task. See [messages](messages.md#will-it-be-read).
- **`--status-note`** reminds a lemon whose brief is `blocked`, `alert`, `merge` or `approve` what it is waiting on, once per turn.
- **`--own-edits`** records a lemon's own edits to the documents it watches, by any tool, and its own `git push`es, so `watch doc` and `watch pr` don't wake it for them.

`lemonaid hooks install` adds the Stop check, the own-edit hooks and a SessionStart reminder of the brief's waiters to Claude Code and Codex at once (`--harness claude` or `codex` for one). Codex needs its new hooks trusted in `/hooks`.

Editing is additive and idempotent, and `--uninstall` removes what lemonaid added.

A background task stops after 30 minutes unless you raise `BASH_MAX_TIMEOUT_MS`. Waiters are background tasks, so do that in [Claude setup](claude.md#2-keep-background-waiters-running).

### Codex

Add the `notify` line at the very top of `~/.codex/config.toml`, and allow the `lemonaid` commands under the automatic approval reviewer if you use it. Both are in [Codex setup](codex.md#setup).

Set `daemon_auto_start = false` under `[features]` in `~/.codex/config.toml`, and start Codex lemons with `codex --no-daemon`. See [the shared-daemon problem](#codex-through-the-shared-daemon).

### Presets and shapes

`lemon start` and `place open` run a lemon preset inside a session shape, both set in `~/.config/lemonaid/config.toml`. A preset names an executable and its default arguments, a shape lists the session's windows, and `[launch]` picks the defaults:

```toml
[tmux-session.shapes.work]
windows = ["emacsclient -nw .", "", ""]
lemon_window = 1

[launch]
default = "claude"
shape = "work"

[launch.presets.claude]
harness = "claude"
args = ["--remote-control", "--thinking-display", "summarized"]

[launch.presets.codex]
harness = "codex"
args = ["--no-daemon"]
```

Swap `emacsclient -nw .` for your editor, or an empty string for a plain shell. `lemon_window` is the 0-based index of the window that holds the lemon. Choose another lemon with `--preset codex`, and add one-off arguments after `--`. See [config](config.md#independent-session-shapes-and-lemon-presets) and [places](places.md).

### The sidebar

`follow_scratch = true` under `[tmux-session]` keeps the inbox in view across every window and session switch the first time you toggle the scratch pane on a tmux server. See [follow mode](tmux.md#follow-mode).

### Existing Claude sessions

`lemonaid claude bootstrap` imports Claude sessions from before lemonaid was installed into the archive. It reads the legacy `sessions-index.json`, which current Claude versions no longer write, so it finds only older sessions. It never makes a running session appear. `--dry-run` shows what it would import.

A session that is already running appears in the inbox when it next takes a prompt or stops, so sending it a message is enough; no restart is needed. A session nobody has spoken to since lemonaid was installed is invisible until then, which is a known gap. `lemonaid inbox list --json` shows unread rows only, so a lemon that is idle or read won't be in it; `lemonaid tmux doctor --unknown` lists running panes the inbox doesn't know about.

### Skills

```bash
lemonaid skills install
```

This installs the `brief`, `watch-doc`, `watch-pr` and `watch-briefs` skills for Claude and Codex. Put your own rules in `~/.lemons/skills/<name>/overlay.md`. See [skills](skills.md).

## 2. Creating the HQ

Start a lemon in a tmux window in a directory you want to treat as home. In that window (or with `lemonaid lemon start SESSION:WINDOW --preset claude`, or `:WINDOW` for a window of your own session), give it a brief of its own:

```bash
lemonaid brief new --self "HQ"
```

This writes `~/.lemons/brief/<date>-hq.md`, attaches it to the lemon that ran it, and gives it a `Lemon-ID`. Write its job under `## Goal`, as the [brief](for-lemons.md#briefs) template shows.

Give it an emoji so its row stands out. Pick one no live session holds:

```bash
lemonaid inbox emojis                          # taken ones
lemonaid inbox emoji --self 🍋
```

Pin it by selecting its row in `lma` and pressing `P`, or run `lemonaid inbox pin --lemon <HQ Lemon-ID>`. `Shift`+`↑` and `Shift`+`↓`, or `inbox pin --move up|down|top|bottom`, order pins. A pinned lemon stays above everything and, in a [group](groups.md), heads it.

Pins belong to a channel, such as `claude:ac7a8776`, not to the lemon's brief. A resumed session, a new Codex thread, or a `lemonaid brief handoff` to another harness can put the lemon on a different channel from the one you pinned. `lemonaid brief handoff`, `/clear` in a Claude lemon, and `lemonaid brief attach` onto a different channel carry the pin to the new channel. A resume that starts a lemon on a channel no brief move went through does not, so after a resume or restart look at the HQ's row and run `lemonaid inbox pin --lemon <HQ Lemon-ID>` if the pin is gone. This is a known gap.

## 3. Adopting running lemons

For each lemon already running, attach a brief and say who its parent is. A lemon's parent is the lemon that hands it work, and the HQ's `children` waiter and `brief children` list follow those links ([lineage](lineage.md)).

Find the lemon first. The inbox list shows unread rows only, so for a read or idle lemon use `tmux doctor --unknown`, or `lma`, to get its session and window:

```bash
lemonaid inbox list --json | jq '.[] | {id, channel, name, tmux: .metadata.tmux_session, cwd: .metadata.cwd}'
```

Then write a brief for it and attach it, on its behalf:

```bash
lemonaid brief new --child "Fix the flaky test" --parent self   # writes an unattached brief
lemonaid brief attach --channel claude:1a2b3c4d <that brief>
# or: --session work:2  (name the window when a session holds several)
# or: --id 1671         (a notification id)
```

`--child` makes a brief for a lemon not started yet, with `Parent:` filled in. Use it for adoption too, then attach. If the lemon already has a brief, attach that and set its parent:

```bash
lemonaid lemon parent --channel claude:1a2b3c4d --set <hq lemon>   # the HQ's Lemon-ID, channel, or `self` from the HQ
```

Put it in a group so the inbox keeps the work together:

```bash
lemonaid group create "Billing" self --tree
lemonaid group add "Billing" <lemon>
```

`create` makes a group and `add` needs one that exists, so a typo is an error rather than a second group. See [groups](groups.md).

Tell each adopted lemon what a brief is and to keep Status and `## Now` true. `lemonaid tell <lemon> "..."` reaches it ([messages](messages.md)). A lemon with a brief also needs one watcher running for it (see `lemonaid watch --self --status`); for a Claude lemon the Stop hook starts its push scout or asks for one.

Two lemons given the same brief ID, usually from copying a brief file, share a mailbox and confuse messaging. Give one a new ID:

```bash
lemonaid brief id --channel <channel> --reroll
```

The old ID keeps working as an alias, so mail already in flight still arrives. The lemon's running mailbox waiter exits and needs rearming. See [rerolling an ID](messages.md#rerolling-an-id).

`lemonaid brief check --all` reports what is wrong with any attached brief.

## 4. The HQ's waiters

A lemon wakes when lemonaid pushes a batch into its session, or when a background task it started exits.

Like any lemon with a brief, the HQ has one watcher for everything its brief lists: its push scout, or `lemonaid watch --self` where no scout can run. Check which with `lemonaid watch --self --status`. See [Watch everything in your attached brief](for-lemons.md#watch-everything-in-your-attached-brief).

The watcher reads the `lemonaid watch` commands under the brief's `## Watching` as its subscriptions. It does not run them. Put the children waiter there, once:

```bash
lemonaid brief waiter add --self "lemonaid watch briefs --children --orphans --self --once"
```

- **`watch briefs --children --orphans --self --once`** wakes when a child's brief Status enters `blocked`, `alert`, `merge`, `approve`, `review` or `done`, or when a `Needs` ask appears or changes. `--orphans` adds briefs no live lemon owns (the lemons you adopted without a parent, and ones whose parent's session is gone). The first run takes the current state as its baseline, and each rearm reports what changed since.
- Without `--orphans`, or without the row at all, a child's status wakes the HQ only when it enters `merge` or `done`.
- Keep one `watch briefs` row. With several, the watcher uses only the last one.
- The watcher always delivers the HQ's mailbox. Don't run `mailbox watch --self` beside it.

While the watcher runs, `watch briefs --self` and `mailbox watch --self` start no second waiter. They print `push scout running` (or `watcher running`) and exit 0. `watch briefs` still records its row under `## Watching`, so the watcher picks it up.

`lemonaid usage --watch` is separate. It wakes when a Claude or Codex limit window crosses a step or is on pace to run out before it resets. Run it as a tracked background task, with `timeout: 2147483647` for Claude (see [Claude setup](claude.md#2-keep-background-waiters-running)), and rearm it after each wake. A detached process (`nohup`, `&`, `disown`) won't wake the lemon. Skip it if you don't watch your usage. Don't list it under `## Watching`: the watcher reports any row other than a `lemonaid watch` or `lemonaid mailbox watch` command as an invalid subscription. So `restore` doesn't rearm it; start it again yourself after a restore.

Details: [watch](watch.md#watching-childrens-briefs) and [usage](usage.md).

`lemonaid watch stop --self` stops all of your waiters. Never `pkill -f` one: the pattern matches every lemon's.

## 5. Restarts and known problems

### After tmux restarts

```bash
lemonaid tmux doctor
lemonaid restore --dry-run
lemonaid restore
```

`restore` rebuilds the sessions the inbox remembers, resumes each lemon in the window it had, and starts each with a prompt to rearm the waiters in its brief. It reports each as working, stuck, exited, or needing a rearm by hand. Pins are keyed by channel, so [check the HQ's pin](#2-creating-the-hq) afterward. See [tmux](tmux.md#surviving-a-crash).

To bring back one lemon, `lemonaid lemon resume <lemon>`. `lemonaid lemon doctor` lists those that are deaf (alive, but with no waiter) or dead.

### Codex through the shared daemon

A Codex session on the shared `codex app-server` records no tty, so lemonaid finds its pane by directory. Two Codex lemons in one directory can't be told apart. Switching to one fails with "No safe tmux destination", and when one ends its row stays until the other does too. Start Codex with `codex --no-daemon`, as in the template above, and keep one lemon per directory if you can. See [Codex troubleshooting](codex.md#switching-to-pane-doesnt-work). The dialog doesn't name this cause yet.

### A brief attached to the wrong thread

An HQ brief can end up attached to a different Codex thread than the one you meant, most often after starting a second Codex in the same directory. Check with `lemonaid brief list`, then fix it by attaching the brief to the right channel, or detaching it first:

```bash
lemonaid brief detach --channel <wrong>
lemonaid brief attach --channel <right> <HQ brief>
```

If the wrong thread is still running, `attach` refuses to take the brief from it; add `--force`, or detach it first as above.

Pin the new channel.

### An archived HQ

Archiving a row (`A`) removes it from the inbox and drops its pin. If the lemon's pane is still alive, run `lemonaid inbox unarchive --lemon <HQ Lemon-ID>` (or press `Z` in the same `lma` session): the row returns unread. Unarchive changes only the inbox row, so it does not restart the harness, re-attach a detached brief, or bring the pin back; run `inbox pin` afterward. If the pane is gone the watcher archives the row again, so press `h` in `lma` to open history, find the session, and resume it instead. Prefer snoozing (`lemonaid inbox snooze --self`) to archiving an HQ.

### A misspelled config key

Lemonaid ignores a config key it doesn't recognize, with no warning. If a setting has no effect, compare its name against [config](config.md) character for character, or run `lemonaid config show`. This is a known gap.

## 6. A starter prompt

Paste this into the HQ lemon as its first message, and change the parts in brackets.

```text
You are my HQ. Read your brief first, then `lemonaid for-lemons`.

Your job:
- Keep track of your children, the leads among them, and orphans (briefs no live
  lemon owns), not their grandchildren; each lead tracks its own. What each is
  doing, what it needs, and whether its brief is true: see
  `lemonaid lemon children --self` and `lemonaid brief children --self`.
- Adopt lemons that have no brief or parent. Ask me before you attach a brief to
  one, then use `lemonaid brief new --child` and `lemonaid brief attach`, and set
  `--parent self`.
- Do not do implementation work yourself. Hand it to a child with a brief,
  using `lemonaid place open` or `lemonaid lemon start`.
- List `lemonaid watch briefs --children --orphans --self --once` under
  `## Watching` in your brief, and keep one watcher running for the brief (see
  `lemonaid watch --self --status`). [Keep `lemonaid usage --watch` running as a
  background task, and rearm it when it wakes you.]
- When a child's Status becomes `blocked`, `alert`, `merge` or `approve`, read its
  brief and tell me in one line what I need to decide.
- Keep your own Status and `## Now` true. Leave Status unset when nothing applies.

My rules for starting, reviewing, merging and cleaning up work: [your rules here,
or a path to the file that holds them].
```

Lemons read their rules at start. Keep the durable ones in a file the prompt points at, so a restored HQ gets them again.
