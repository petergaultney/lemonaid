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
- **`--waiter-check`** adds a Stop hook that stops a lemon with a brief from ending its turn while its `lemonaid inbox watch --self` isn't running. An HQ with children is also held to a running `watch briefs --children` waiter. See [messages](messages.md#will-it-be-read).
- **`--status-note`** reminds a lemon whose brief is `blocked`, `alert`, `merge` or `approve` what it is waiting on, once per turn.
- **`--own-edits`** records a lemon's edits to a document it watches so `watch doc` doesn't wake it for them. Skip it if you don't use `watch doc`.

Editing is additive and idempotent, and `--uninstall` removes what lemonaid added.

A background task stops after 30 minutes unless you raise `BASH_MAX_TIMEOUT_MS`. Waiters are background tasks, so do that in [Claude setup](claude.md#2-keep-background-waiters-running).

### Codex

Add the `notify` line at the very top of `~/.codex/config.toml`, and allow the `lemonaid` commands under the automatic approval reviewer if you use it. Both are in [Codex setup](codex.md#setup).

Start Codex lemons with `codex --no-daemon`. See [the shared-daemon problem](#codex-through-the-shared-daemon).

### Templates

`lemon start` and `place open` run a command from `[tmux-session.templates]` in `~/.config/lemonaid/config.toml`. Name each template for its harness, and point `default` at the one you use most:

```toml
[tmux-session]
resume_window = 1

[tmux-session.templates]
claude = ["emacsclient -nw .", "claude", ""]
codex = ["emacsclient -nw .", "codex --no-daemon", ""]
default = "claude"
```

Each list is a window layout (swap `emacsclient -nw .` for your editor, or an empty string for a plain shell), and `resume_window` is the 0-based index of the window that holds the harness. See [config](config.md#tmux-sessiontemplates) and [tmux](tmux.md).

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

Start a lemon in a tmux window in a directory you want to treat as home. In that window (or with `lemonaid lemon start SESSION:WINDOW --harness claude`), give it a brief of its own:

```bash
lemonaid brief new --self "HQ"
```

This writes `~/.lemons/brief/<date>-hq.md`, attaches it to the lemon that ran it, and gives it a `Lemon-ID`. Write its job under `## Goal`, as the [brief](for-lemons.md#briefs) template shows.

Give it an emoji so its row stands out. Pick one no live session holds:

```bash
lemonaid inbox emojis                          # taken ones
lemonaid inbox emoji --self 🍋
```

Pin it by selecting its row in `lma` and pressing `p`. `Shift`+`↑` and `Shift`+`↓` order pins. A pinned lemon stays above everything and, in a [group](groups.md), heads it.

Pins belong to a channel, such as `claude:ac7a8776`, not to the lemon's brief. A resumed session, a new Codex thread, or a `lemonaid brief handoff` to another harness can put the lemon on a different channel from the one you pinned. After any resume or restart, look at the HQ's row and pin it again if the pin is gone. This is a known gap: nothing carries a pin across a channel change.

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

Tell each adopted lemon what a brief is and to keep Status and `## Now` true. `lemonaid tell <lemon> "..."` reaches it ([messages](messages.md)). A Claude lemon with a brief must also keep `lemonaid inbox watch --self` running; the Stop hook enforces it.

Two lemons given the same brief ID, usually from copying a brief file, share an inbox and confuse messaging. Give one a new ID:

```bash
lemonaid brief id --channel <channel> --reroll
```

The old ID keeps working as an alias, so mail already in flight still arrives. The lemon's running inbox waiter exits and needs rearming. See [rerolling an ID](messages.md#rerolling-an-id).

`lemonaid brief check --all` reports what is wrong with any attached brief.

## 4. The HQ's waiters

A lemon wakes only when a background task it started exits. The HQ keeps three running:

```bash
lemonaid watch briefs --children --orphans --self --once
lemonaid inbox watch --self
lemonaid usage --watch
```

- **`watch briefs --children --orphans --self --once`** wakes when a child's brief Status enters `blocked`, `alert`, `merge`, `approve`, `review` or `done`, A change to a child's `Needs` alone doesn't wake it. `--orphans` adds briefs no live lemon owns (the lemons you adopted without a parent, and ones whose parent's session is gone), and their `Needs` changes do wake. The first run takes the current state as its baseline, and each rearm reports what changed since. Without `--orphans` it wakes only on `merge` and `done`.
- **`inbox watch --self`** wakes when another lemon, or you, `tell`s the HQ something.
- **`usage --watch`** wakes when a Claude or Codex limit window crosses a step or is on pace to run out before it resets. Skip it if you don't watch your usage.

Each prints what woke it and exits. Read it, act, and rearm the same command.

Run them as tracked background tasks of the harness, with `timeout: 2147483647` for Claude. A detached process (`nohup`, `&`, `disown`) won't wake the lemon, and the Stop hook can't tell it is running. If one stops, rearm it. Lemonaid records `watch` waiters under `## Waiters` in the brief when they start. List the others there yourself with `lemonaid brief waiter add --self "<command>"`, since `restore` rearms only what the brief lists.

The Stop hook accepts any running `watch briefs --children` waiter, including the `--orphans` form. It does not check which statuses it wakes on. Details: [watch](watch.md#watching-childrens-briefs) and [usage](usage.md).

`lemonaid watch stop --self` stops all of your waiters. Never `pkill -f` one: the pattern matches every lemon's.

## 5. Restarts and known problems

### After tmux restarts

```bash
lemonaid tmux doctor
lemonaid restore tmux --dry-run
lemonaid restore tmux
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

Archiving a row (`a`) removes it from the inbox, and there is no command that unarchives. Press `z` in the same `lma` session to undo the archive. Otherwise press `h` in `lma` to open history, find the session, and resume it, which starts it again, or search with `/`. Then re-attach its brief if it was detached, and pin it. This is a known gap. Prefer snoozing (`lemonaid inbox snooze --self`) to archiving an HQ.

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
- Keep these running as background tasks, and rearm each when it wakes you:
  `lemonaid watch briefs --children --orphans --self --once`,
  `lemonaid inbox watch --self`, [and `lemonaid usage --watch`].
- When a child's Status becomes `blocked`, `alert`, `merge` or `approve`, read its
  brief and tell me in one line what I need to decide.
- Keep your own Status and `## Now` true. Leave Status unset when nothing applies.

My rules for starting, reviewing, merging and cleaning up work: [your rules here,
or a path to the file that holds them].
```

Lemons read their rules at start. Keep the durable ones in a file the prompt points at, so a restored HQ gets them again.
