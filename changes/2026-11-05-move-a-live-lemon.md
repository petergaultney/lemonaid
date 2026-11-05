# Minor

#### Added

- **`lemonaid lemon move <lemon> <place>` moves a live lemon into another place.** It resumes the same Claude session or Codex thread in the destination directory and workspace, keeps its Lemon-ID, brief and links, and closes the old pane when only a shell is left there. It refuses to move a Claude lemon into a directory Claude doesn't trust yet, since the resumed lemon would stop at Claude's folder-trust prompt, unless the directory's places root sets `claude_trust = true`; then the move records that trust first. Each move is recorded in the audit log as `lemon-move`.

#### Changed

- **A Codex resume always names its directory with `--cd`, and `lemonaid claude resume` resumes in the directory the inbox last recorded.** Codex otherwise stops at a directory dialog when the session last worked somewhere else.
