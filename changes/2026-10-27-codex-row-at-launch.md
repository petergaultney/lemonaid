# Patch

#### Fixed

- **A new Codex lemon shows in the inbox as soon as it starts.** It used to get its row, and the brief that `place open --brief` or `lemon start --brief` left waiting on its window, only when its first turn ended; until then `lemon doctor` and `brief children` called it dead. Codex's SessionStart hook now records the row with its pane. Needs the SessionStart hook from `lemonaid hooks install --harness codex`.
