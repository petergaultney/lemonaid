# Multi-lemon development

The lemonaid plan manager (HQ) owns the post-merge handoff in Peter's local
development setup. As soon as a change lands on main:

1. Update the local main worktree. Tell authors of other active lemonaid branches
   to rebase on it; the author handles their own working tree and conflicts.
   A reviewer rechecks any PR whose head moves.
2. Find the installed tool environment with `uv tool list --show-paths`, then
   read its `site-packages/_editable_impl_lemonaid.pth` to identify the source
   checkout. Keep that checkout at least as current as main.
   It may point to a feature branch instead when Peter is actively testing that
   feature, but that branch must also include current main. Use Peter's trial
   instructions and the actual installed source to choose the target.
3. Before activating merged code with a new runtime dependency, install that
   dependency into the tool environment with
   `uv pip install --python ~/.local/share/uv/tools/lemonaid/bin/python <package>`.
   An editable source change alone does not install new dependencies. Verify
   the CLI starts, then restart long-running TUI/sidebar processes with
   `lemonaid tmux scratch --restart` so they load the new code.

Do not silently replace a feature branch Peter is testing. If the installed
source or intended trial is unclear, confirm the target before switching it.
