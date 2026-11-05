# Minor

- **`lemonaid run --self -- <command>` wakes the lemon with the command's exit status, wherever the command runs.** It records `lemonaid watch command --wait <pid>` in the brief, so the exit arrives in the next batch and the line then removes itself; use `--lemon <Lemon-ID>` from a new tmux window or `nohup`. A wrapper killed outright is still reported, and `watch command --wait <pid>` watches a process already running, with its status unknown.
- **`watch file --deadline 45m` (or an ISO time) reports once if nothing changed by then,** so a marker that never appears no longer waits silently. A duration counts from the first arm, not each rearm.
