# Patch

#### Fixed

- **A quiet `git push` after a multi-line quote is caught.** A command whose quoted commit message ran over several lines, or that continued a line with a backslash, got its quiet push past the check, so the lemon's own PR watch later woke it for that push.
- **Heredoc text and `git stash push -q` are no longer taken for quiet pushes.** Only `push` as git's subcommand counts, after any of git's own options, such as `--git-dir <path>`.
