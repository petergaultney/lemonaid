# Minor

#### Added

- **The default checker challenges `merge` while its PR conflicts with its base or has an unresolved review thread whose last word is another lemon's or another account's, and `approve` once you have approved the PR.**
- **The default checker challenges `blocked` or `alert` with no `Needs`, or with a `Needs` link to a file or heading that doesn't exist.** It never reads what the linked section says.
- **A checker of your own can reuse the default rules.** The default checker is now a rule set in stages (`rules.DEFAULT`): replace or extend one stage and run it with `rules.main(rules=...)`. See `docs/tasks.md`.
- **New checker facts:** a PR's `mergeable`, `unresolved` and `user_verdict`; a brief's `signing_names`, `status_since`, `needs_since` and `needs_links`; and each linked file's `exists`, `modified_at` and `headings`.
