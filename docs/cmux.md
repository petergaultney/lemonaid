# cmux Integration

Lemonaid switches to the [cmux](https://cmux.com) workspace and surface (tab) where a notification came from, and resumes the session in a new workspace when it has none. Switching needs no cmux configuration; [Setup](#setup) covers the hooks lemonaid needs anywhere, and running `lma` in cmux's Dock.

## How it works

A hook run inside cmux sees `CMUX_SURFACE_ID` and records the notification with `switch_source = "cmux"`, the session's tty, and its surface (`cmux_surface`). Selecting it in `lma`, and the watcher deciding whether it has ended, both find the session by one rule:

1. **The recorded surface, while it still has the recorded tty.** Either alone can pass to something else: a tty name to another surface, a surface to another program.
2. **A surface cmux has bound to the session, where its agent (`claude`, `codex`, ...) runs.** cmux records the agent session each surface runs, and resumes it there after a restart, on a new tty. A binding outlives its agent, which is why the agent has to be running.
3. **For a row recorded without a surface, the surface with its tty.**

A session run in tmux inside cmux is recorded as tmux, and is switched to by the [tmux integration](tmux.md).

### Switching

Selecting a notification, or an archived session in history, uses the rule too. In history, a session the rule finds running is brought back to the inbox rather than resumed a second time.

Selecting a notification focuses the surface found with `cmux focus-panel`, which also brings its workspace forward. When the session runs on more than one surface, lemonaid does nothing, since resuming would make a third copy. When it runs on none, lemonaid resumes it with its harness's resume command (see `resume_command` in [config.md](config.md)) in a new workspace rooted at its directory. A session with no resume command, or whose directory is gone, is left alone. If `ps` cannot say what runs on a surface, lemonaid neither switches nor resumes.

### The watcher

The watcher asks `cmux tree --all` once per tick, with a half-second timeout. Step 2 needs a `cmux list-panels` for each workspace, about 0.7 s for 30 of them, so it runs only for a session that is not where it was recorded, and the watcher reuses that answer for 10 seconds. A session found on another tty is judged there; a session found nowhere is archived. If cmux does not answer, nothing is archived, and that is logged once until cmux answers again.

## Requirements

Lemonaid calls the `cmux` CLI, so it must be on `PATH` and able to reach the cmux socket. Processes started inside cmux can; for anything else, see cmux's socket settings (`cmux docs settings`).

## Setup

### 1. Install the harness hooks

Lemonaid knows a session only once one of its hooks has fired, in cmux as anywhere else. Set them up for each harness you run: [Claude Code](claude.md), [Codex](codex.md), [OpenCode](opencode.md). A Claude session that is already running picks up new hooks without a restart, and appears at its next prompt.

### 2. Turn on the Dock

Run `lma` in the cmux Dock, the right sidebar's terminal panel. cmux keeps a Dock for each window as well as for each workspace, and the window's Dock stays in view whichever workspace is selected. That is the job the [tmux scratch pane and follow mode](tmux.md#scratch-pane) do, so cmux needs neither.

Current cmux has the Dock on by default. Some builds (0.64, for one) keep it behind a beta toggle, the Dock switch in the Beta Features section of cmux's Settings. From a shell:

```bash
defaults write com.cmuxterm.app rightSidebar.beta.dock.enabled -bool true
```

`cmux.json` cannot set it, and cmux applies it without a restart. While it is off, `cmux new-pane --placement dock` fails with "Dock placement is disabled".

### 3. Start `lma` in the Dock

Show the Dock with the right sidebar's mode switcher, the command palette's "Show Sidebar Dock", or `cmux right-sidebar set dock`. Its New Terminal button, or `cmux new-pane --placement dock`, adds a terminal; run `lma` in it. cmux restores the Dock, `lma` included, when it restarts.

To have every new window's Dock start with `lma`, add a control to `~/.config/cmux/dock.json`:

```json
{
  "controls": [
    { "id": "lma", "title": "lemonaid", "command": "~/.local/bin/lma" }
  ]
}
```

cmux runs a Dock command in a non-interactive login shell, which does not read `~/.zshrc` or `~/.bashrc`, so a bare `lma` is "command not found" unless your login profile puts `uv`'s tool directory (`uv tool dir --bin`) on `PATH`. The file only seeds a Dock with no saved layout, such as a new window's; a Dock you have arranged is restored as you left it.

Run in cmux, `lma` shows only the notifications from cmux, plus headless ones, as it does for tmux and WezTerm.

### 4. Get to the inbox and to a lemon

By default `⌘⇧E` focuses the right sidebar, where `lma` runs, and `⌘⌥B` shows or hides it. Remap either in `~/.config/cmux/cmux.json`. Inside `lma`, Enter on a row runs `cmux focus-panel` on that session's surface, which also brings its workspace forward.

cmux's terms against tmux's:

| cmux | Nearest tmux equivalent |
|---|---|
| Window (a macOS window, with its own sidebar and workspaces) | client or server |
| Workspace (a sidebar entry; `⌘1` to `⌘8` jump to them) | session |
| Pane (a split) | pane |
| Surface (a tab inside a pane) | roughly a window, but each pane has its own tab bar |

`⌘<n>` jumps between workspaces, not between the tabs inside one, so it replaces a tmux window-number binding only if each lemon has a workspace of its own instead of a window in a shared session.

## Limitations

- **No back navigation.** There is no `lemonaid cmux back` yet.
- **tmux-only features stay tmux-only:** the brief sidebar and session templates. A resumed session gets a plain workspace, not a template's layout.
