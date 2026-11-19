# Patch

#### Fixed

- **A Codex lemon whose rollout Codex compressed can be resumed.** Codex zstd-compresses idle rollouts to `.jsonl.zst` and still resumes them, but `lemon resume`, `tell --wake`, `lemon archived`, restore and `tmux doctor` looked only for `.jsonl` and refused with "its conversation's transcript is gone".
- **A new Codex thread no longer takes over the channel of an older lemon on the same pane whose rollout Codex compressed.** lemonaid treated the older thread as having no conversation, so the older lemon could be resumed into the newer one's.
