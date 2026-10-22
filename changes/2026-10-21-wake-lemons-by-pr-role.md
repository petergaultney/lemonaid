# Minor

#### Changed

- **`watch --self` wakes a lemon for a PR's events by its role on that PR.** An author wakes for everything but ready-for-review and passing CI, a reviewer for pushes and merge or close, and a parent for merge or close only; `[watch.roles.<role>] wake` changes a role's list, and `watch --self --status` prints each PR's role.
- **Events that don't wake a lemon arrive with the next one that does,** listed as `Seen without waking you`.
- **A `### PRs` row no longer asks for passing CI.** A failure still wakes the author and tells it to clear a `merge` status, which no longer waits for green CI; the review template's watch line uses `--role reviewer` instead of `--comments --ci`.
- **A GitHub outage is reported once per lemon, after `[watch] github_debounce`** (10 minutes by default) of failed reads with none succeeding, instead of once per PR after three failures.
- **A child's Needs ask no longer wakes its parent's `watch --self`.** A child blocked on its user stays out of its parent's way; it still wakes the parent on `merge` and `done`, and a `### Lemons` row for the child can add `needs` back.
- **`watch pr` no longer suggests adding `--ci`** when checks are pending.

#### Added

- **A quiet `git push` no longer wakes its own author.** lemonaid recognizes a lemon's own push only by the heads it prints, so in Claude Code the hooks remove `-q`/`--quiet` before the push runs and tell the lemon not to push quietly; a push that sends stderr to `/dev/null`, or a Codex lemon's quiet push, is refused.

- **`watch pr --role author|reviewer|parent`** sets the role explicitly; otherwise it comes from a `Reviewer (` signature, a Review cell that is the brief's `Output-Doc:`, or a child authoring the PR.
