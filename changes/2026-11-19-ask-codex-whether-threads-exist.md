# Patch

#### Changed

- **Restore, `lemon resume`, `tell --wake`, `lemon archived` and `tmux doctor` ask Codex whether a Codex lemon's conversation can still be resumed.** One short-lived `codex app-server` answers for every lemon in the run; when Codex can't be asked, lemonaid looks for the rollout file as before. A thread Codex has archived counts as gone, since `codex resume` refuses it until it is unarchived.
