# Minor

#### Added

- **A brief's PR links wake its lemon when they merge or close.** Every pull-request URL in a brief, not just `### PRs` rows, subscribes its lemon to the merge or close, and the event asks whether the link is still relevant for its user. A link added after the PR closed asks nothing, and a PR listed under a `No nudge` heading is never asked about. `[watch.pr] link_nudge = false` turns it off.
