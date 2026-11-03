# Patch

#### Changed

- **A PR's CI-failed notice names what failed.** Each failed check is listed with its job page and the errors it annotated, such as a failing test's file, line and assertion; a check with none gives the `gh run view --job <id> --log-failed` command for its log.
