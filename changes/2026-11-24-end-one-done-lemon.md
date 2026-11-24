# Minor

#### Added

- **`lemonaid lemon end <lemon>` ends one lemon, such as a reviewer whose PR merged, without tossing the place it shares: its harness, waiters and own pane go, and its brief moves to the attic.** It ends only a lemon whose brief's Status is one you expect, `done` unless you pass `--expect`, and otherwise prints the Status it found.
- **When a PR you watch merges or closes, its event names each lemon you may now end, with the command.** These are the lemons whose brief names you as `parent:` and that share their tmux session with another live lemon, such as an author's reviewers, once their work is done.

#### Fixed

- **A Codex lemon whose turn ends in an error, such as a response OpenAI refused to show, no longer stays mid-turn.** Codex reports no end for such a turn, so lemonaid reads it from the lemon's transcript, and the card says `Turn failed: <reason>`.

#### Changed

- **`brief children` lists the lemons whose brief names you as `parent:`, such as reviewers started with `--parent parent`, with the `lemon end` command for each.**
- **`brief children` leaves out a child whose brief is in the attic, and such a child no longer holds up its parent's cleanup.** `--all` still lists it, as `cleaned`.
