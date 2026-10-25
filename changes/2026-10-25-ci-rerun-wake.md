# Patch

#### Fixed

- **`watch pr --ci` wakes again when a re-run fails on the same head.** A CI failure was reported once per head commit, so `gh run rerun --failed` failing again went unnoticed; each check's finish time now tells a new failure from one already reported.
