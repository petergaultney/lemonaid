# Minor

#### Added

- **A brief given at start reaches its lemon in any terminal.** `lemon start --brief` puts a launch token in the new shell's environment, and the brief goes to the first lemon whose hooks record it; tmux keeps waiting on the window too.
- **`lemon start` with no window starts a lemon beside you**, in the current directory: a new window of your own tmux session, or a new tab in WezTerm. It prints where it went, and `--json` adds `front_end` and `where`.
