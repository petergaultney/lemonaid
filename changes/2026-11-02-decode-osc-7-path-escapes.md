# Patch

#### Fixed

- **A tmux tab label decodes `%XX` escapes in an OSC 7 path.** oh-my-zsh and xonsh percent-encode the path, so a directory named `with space` showed as `with%20space`. A path from `#{pane_current_path}` keeps its `%` characters, and the OSC 7 snippets in `docs/tmux.md` now escape `%` as `%25`.
