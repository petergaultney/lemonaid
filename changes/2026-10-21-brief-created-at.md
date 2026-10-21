# Minor

#### Added

- `brief new` writes `type: Brief` and `created: { at: ..., by: ... }` into every brief it creates. `at` is an ISO 8601 time with UTC offset, and `by` is the WordyBin of the lemon running the command when it has a named brief. They are header lines under `Brief-ID:`, and briefs made earlier are not backfilled.
