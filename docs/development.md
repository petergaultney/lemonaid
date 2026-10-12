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

## Releases

A merge to main that brings a version with no `v<version>` tag releases it:
`.github/workflows/release.yml` runs once the `test` workflow passes on main,
publishes the build to PyPI as `lemonaid-inbox`, and creates the tag and a
GitHub Release whose notes are that version's CHANGES.md section
(`scripts/changelog-section.py`). A merge that leaves the version alone
releases nothing, and a version without a CHANGES.md section fails the run.

PyPI accepts the upload through trusted publishing from the `pypi`
environment, so the repo holds no token. A failed run can be re-run from the
Actions page: the PyPI step skips files already uploaded, and a Release left
as a draft is finished rather than created again.

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

Widgets:

- `inbox_content.py` (`InboxContent`): the panes under the header. It knows which view is
  up, the search state, cards or columns, the notes and the status line.
- `inbox_list.py` (`InboxList`): the main and other-terminals tables and the fold line. It
  owns the fold, the arranger, drawn group headers and where the cursor follows.
- `history_table.py`, `snoozed_table.py`: the history and snoozed lists, with resume and wake.
- `brief_pane.py` (`BriefPane`): the brief shown in place of the inbox, browsing from row to
  row, and switching the main pane behind it.

What a refresh reads and draws:

- `inbox_frame.py`: the database read; `inbox_arrange.py`: the arranger process;
  `inbox_entries.py`: rows and group headers in drawing order.
- `inbox_main_table.py`, `inbox_draw.py`: the main table, the other-terminals table, the fold line.
- `history_rows.py`, `snoozed_rows.py`, `row_cells.py`, `inbox_rows.py`, `row_parts.py`:
  the cells of one row; `cards.py` folds them into a card.
- `table_rows.py`, `table_columns.py`, `table_setup.py`, `table_layout.py`, `layout.py`:
  bringing a `DataTable` in line with its rows, and its columns and widths.
- `styles.py`, `status_line.py`, `search_archive.py`, `view_modes.py`.

What the keys do:

- `bindings.py`: the key table built from config, and which actions are allowed when.
- `inbox_edits.py`, `edit_dialogs.py`: undoable row changes and the dialogs that ask for them.
- `inbox_groups.py`, `group_dialogs.py`, `inbox_pins.py`: groups and pins.
- `inbox_switch.py`, `history_resume.py`: switching to a session, and resuming one from history.
- `table_nav.py`, `cursor_target.py`, `row_keys.py`: moving the cursor and reading what it is on.
- `focus.py`, `session_names.py`, `watcher_hooks.py`, `claude_patch.py`: tmux focus, session
  titles, the transcript watcher's database callbacks, and the Claude patch.
