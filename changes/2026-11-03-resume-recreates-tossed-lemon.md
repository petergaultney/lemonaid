# Minor

#### Added

- **`lemon resume --recreate` brings back a lemon whose place was tossed.** It revives the lemon's archived brief onto its old session, recreates its directory through the root's hooks and its tmux session under the recorded name, then resumes it. It refuses when the places log doesn't say which place the directory was, rather than resuming in a parent directory.
