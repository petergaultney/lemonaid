# Minor

#### Added

- **`lemonaid watch reviews --wait` wakes a lemon when someone requests your review.** It reports, once each, a PR newly requesting your review or newly assigned to you, with its repo, number, title, author and URL; `--scope org:NAME` or `repo:OWNER/NAME` narrows the search. A lemon subscribes with a `## Watching` line in its brief; the source never changes anything on GitHub.
