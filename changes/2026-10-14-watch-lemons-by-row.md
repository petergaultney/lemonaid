# Minor

#### Added

- **`### Lemons` rows watch any lemon.** `brief lemon add|set|rm` lists a lemon by Lemon-ID, channel or brief name, with the Statuses (or `needs`) that wake you, and `watch --self` and the push scout report its Status and Needs changes like a child's. An explicit row for a child replaces its default wake statuses.
- **Watched lemons report an exit once.** A child or listed lemon whose harness exits, whose tmux session or directory is gone, or that goes deaf is reported once per occurrence, unless its brief is `done`. `watch briefs --children` reports them too.

#### Changed

- **A child's changed Needs wakes `watch --self`.** It used to advance the baseline silently.
