# Minor

#### Changed

- The scout host now keeps one private `codex app-server` running and writes what Codex has stored about each Codex lemon's thread to a file, so lemonaid reads answers about Codex threads instead of starting Codex for each question. A thread not in that file yet is asked of a short-lived app-server, and the scout host is started so it is read from then on.
- A Codex thread is counted as gone only when Codex says so. When Codex can't be asked, restore, `lemon resume` and `tell --wake` no longer refuse a lemon because its rollout file can't be found.
