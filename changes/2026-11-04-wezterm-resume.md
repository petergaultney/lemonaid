# Minor

#### Added

- **Autoresume and `lemon resume` work in WezTerm.** A dead lemon is resumed in a new tab of its recorded workspace, recreating the workspace if it is gone, and an idle one with no waiter has its wake prompt typed in, as in tmux. Hooks now record each lemon's WezTerm pane, workspace and instance, so a lemon that started before this needs one turn before lemonaid can resume it.
