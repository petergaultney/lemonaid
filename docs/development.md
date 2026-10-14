# Multi-lemon development

The lemonaid plan manager (HQ) owns the post-merge handoff in a local
development setup. As soon as a change lands on main:

1. Update the local main worktree. Tell authors of other active lemonaid branches
   to rebase on it; the author handles their own working tree and conflicts.
   A reviewer rechecks any PR whose head moves.
2. Find the source the tool was installed from. `uv tool dir` gives the tool
   environments' root, and `lemonaid-inbox/uv-receipt.toml` under it names the
   source as `editable = "<path>"` or `directory = "<path>"`.
   Choose the target from the user's trial instructions and that source. It is
   usually main, and may be a feature branch the user is actively testing, but a
   branch must also include current main.
3. Activate the new code.
   - **Editable install**: the tool runs from the checkout, so keep that
     checkout at least as current as the target. A new runtime dependency is
     not installed by a source change; add it with
     `uv pip install --python ~/.local/share/uv/tools/lemonaid-inbox/bin/python <package>`.
   - **Non-editable install**: the tool environment holds a copy built at
     install time, so updating the checkout changes nothing. Update the
     checkout, then reinstall from it with `uv tool install --reinstall <path>`,
     which also installs new dependencies.

   Verify the CLI starts, then restart long-running TUI/sidebar processes with
   `lemonaid tmux scratch --restart` so they load the new code.

Do not silently replace a feature branch the user is testing. If the installed
source or intended trial is unclear, confirm the target before switching it.

## Changes and releases

A PR describes its change in one file under `changes/`, and never adds a version to
`pyproject.toml` or edits `CHANGES.md` or a change file already on main, so two PRs
conflict only where their code does. The file is `changes/YYYY-MM-DD-two-to-six-word-title.md`,
dated the day the work started. Its first line is `# Patch`, `# Minor` or `# Major`, and
the rest is its changelog entry. `changes/README.md` has the format. A PR that changes
only docs or tests gets no file and takes the `no-change-file` label. The `changes`
workflow (`.github/workflows/changes.yml`, `scripts/check-change-file.py`) enforces this.

**Merging a PR publishes nothing.** Its change file waits on main until the next release.

A release is made of the change files added since the previous `v*` tag. Its version is
that tag's raised by the highest bump among them, and its notes are their entries in
date order. `scripts/release.py version` and `scripts/release.py notes` print both and
change nothing. Files keep their dated names after a release.

`.github/workflows/release.yml` releases daily at 13:00 UTC, and on demand: run it from
the Actions tab or with `gh workflow run release.yml` to release mid-day. A run takes the
newest main commit whose `test` workflow passed and, if change files were added since the
highest tag, pushes the next version's tag to that commit. It builds from the tag,
publishes to PyPI as `lemonaid-inbox`, and creates a GitHub Release with the notes. It
never commits to main or opens a PR.

`pyproject.toml` has no version: `hatch-vcs` takes it from the nearest `v*` tag, so a
build from a later commit is a dev version such as `0.116.1.dev3+g1a2b3c4`, and a tree
without git history builds as `0.0.0`. `CHANGES.md` keeps the history through 0.115.3.

PyPI accepts the upload through trusted publishing from the `pypi`
environment, so the repo holds no token. A run that fails after pushing its tag
is finished by the next run, scheduled or manual: a tag with no published
GitHub Release is built and published again, the PyPI step skips files already
uploaded, and a Release left as a draft is finished rather than created again. A
tag that can never finish (its build fails every time) holds up every later release:
fix the cause on main and run the workflow again, or delete the tag to abandon that
release.

The tool environment named `lemonaid` from before the rename has to be
removed once (`uv tool uninstall lemonaid`) before installing
`lemonaid-inbox`, from a checkout or from PyPI.

## Nothing is specific to one person

Lemonaid's code, help text, docs and defaults name no particular user.
The Needs heading is `### Needs` with an optional one-word name after it (`### Needs Sam`), and code refers to "the user", never a name.
A person's name belongs only in test data, as an example, and a new test that depends on the Needs heading should not use the maintainer's name for it.
Opinions about how one person works go in that person's own overlays and instructions, not here.

## Keeping tmux replaceable

Code outside `src/lemonaid/tmux/` should not run `tmux` or import `lemonaid.tmux`, so another terminal UI can take its place.
`tests/test_tmux_ratchet.py` fails when a file outside `tmux/` does either unless the file is in its `_ALLOWED` set, which holds the files that still do.
A change that removes the last such use from a file deletes the file from `_ALLOWED` (the test also fails on stale entries), and a new file may not be added.
Code that needs a tmux command calls a function in `src/lemonaid/tmux/`, and those functions run it through `tmux.run`.

## Where the inbox TUI's code lives

`inbox/tui/app.py` routes input: key bindings, `action_*` methods, mouse and
message handlers, refresh ticks and the brief overlay. Each action decides what
should happen and hands the work to the widget or module that owns it. The
widgets keep their own state; plain modules take explicit arguments.

Beside `app.py` sit the pieces the whole app uses: `inbox_content.py` (`InboxContent`, the
panes under the header: which view is up, the search, cards or columns, the notes and the
status line), `bindings.py` (the key table and which actions are allowed when), `styles.py`,
`utils.py`, `notes.py`, the help and error screens, and `claude_patch.py`.

The subpackages, each named for what it owns:

- `live/`: the inbox list. `inbox_list.py` (`InboxList`) owns the main and other-terminals
  tables, the fold, the arranger and where the cursor follows. A refresh reads the database
  (`inbox_frame.py`), asks the arranger (`inbox_arrange.py`), orders rows and group headers
  (`inbox_entries.py`) and draws them (`inbox_main_table.py`, `inbox_draw.py`).
- `watchers/`: background work the app polls: tmux focus (`focus.py`), session titles
  (`session_names.py`), and the transcript watcher's database callbacks (`watcher_hooks.py`).
- `rows/`: one session's row: its cells (`row_cells.py`, `inbox_rows.py`, `row_parts.py`),
  its card (`cards.py`), the cached brief details both draw from (`brief_cards.py`,
  `brief_rows.py`), and bringing a table in line with its rows (`table_rows.py`).
- `tables/`: the `DataTable`s: columns and widths, row keys, and moving the cursor across tables.
- `briefs/`: the brief opened up: the scratch pane's brief view, its questions,
  `brief_pane.py` (`BriefPane`, the brief shown in place of the inbox), and the popup.
- `edits/`: undoable changes to a row, groups and pins, and the dialogs that ask for them.
- `views/`: the history, snoozed and usage views, and `view_modes.py`, which says how each
  changes the footer.
- `switching/`: putting the terminal on a session, resuming one from history, and what to
  show when either fails.

The subpackages import one way: `rows` and `tables` sit at the bottom, and nothing below
`app.py` imports `bindings`.
