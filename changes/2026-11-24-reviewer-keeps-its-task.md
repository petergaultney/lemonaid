# Patch

#### Changed

- **A review brief now names only the task rule that applies.** `lemonaid brief new --child --template review` tells the reviewer either to hand back the PR's own task or to keep its own, never both. A hidden (reviewer) brief that sets `done` while it holds a task about a PR is refused, so the task never reaches the lead as a check.
