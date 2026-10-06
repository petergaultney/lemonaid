# Patch

#### Fixed

- **The OSC 7 shell snippets in `docs/tmux.md` now set `#{pane_path}`.** They wrapped OSC 7 in a tmux passthrough sequence, which tmux does not read. They now print a plain OSC 7 before each prompt.
