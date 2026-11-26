# Minor

#### Added

- **Inbox commands that change a session say whose it was.** `rename`, `emoji`, `pin`, `unpin`, `archive`, `unarchive` and `snooze` print the session's Brief-ID and directory and, when the caller can be told, whether it was its own; `rename` and `emoji` also say what they replaced. A lemon that changed another lemon's session is told who it is and to use `--self` for its own.
