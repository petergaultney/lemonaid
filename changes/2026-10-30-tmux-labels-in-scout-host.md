# Minor

#### Changed

- **tmux tab labels come from the scout host instead of a process per tab.** `lemonaid tmux labels`, run from the tmux config, has the host keep each window's label in `@lemonaid_label` and `@lemonaid_label_current` through one control-mode client. It relabels a window only when its pane changes. The new formats in `docs/tmux.md` read those options, so drawing the status line starts no process. The `#()` scripts still work for older configs.
