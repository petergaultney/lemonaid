# Patch

#### Fixed

- **Watchers no longer read GitHub themselves while the shared PR poller runs.** A poller that fell behind, as it did after every quota pause, used to send each lemon's watcher to GitHub every minute for every PR, which used up the hourly quota within minutes.
- **The shared PR poller keeps up with a busy evening of watched PRs.** It reads changed PRs four at a time, no longer re-reads a PR in full each minute while its CI runs or every 15 minutes once it is merged or closed, and confirms unchanged PRs before the slow reads start.
