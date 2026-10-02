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
