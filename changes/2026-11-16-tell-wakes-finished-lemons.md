# Minor

#### Added

- **`tell --wake` wakes a lemon that finished.** It brings back a `done` or archived lemon the way `lemon resume --recreate` does, and the lemon reads the message once it is up; rerunning a plain `tell` with `--wake` doesn't queue the message twice.
- **`tell --wake-parent` reaches the nearest lemon above one that can't be woken.** `--wake` names it when a lemon has no recorded session, no transcript, or a directory lemonaid can't put back.
- **`lemon archived` lists archived lemons** with their last Status and `## Now` line, and whether `tell --wake` could bring each back.

#### Fixed

- **`tell` to a lemon whose brief is archived queues the message.** It used to fail with "found 0" and queue nothing; it now says how to wake the lemon.
- **`lemon resume` refuses a lemon whose transcript is gone.** A resume would have started an empty conversation under its name without reporting an error.
