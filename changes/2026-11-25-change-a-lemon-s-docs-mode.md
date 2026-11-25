# Minor

`lemonaid docs mode` shows or changes a running lemon's docs mode, by `--self` or by session. Claude takes the new mode at its next resume through lemonaid, and Codex at its next compaction or resume.

A Claude resume now builds its docs flags from the session's mode at that time, so a lemon switched to `classic`, or one whose `[docs] roots` were removed, no longer resumes with its old package prompt and `claudeMdExcludes`.
