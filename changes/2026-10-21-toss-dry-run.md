# Minor

#### Changed

- **`place toss --json` alone no longer tears anything down; it prints the preview and exits 2.** Add `--yes` (`--json --yes`) to tear down, as `--yes` alone always did. Callers that passed only `--json` must add `--yes`.

#### Added

- **`place toss --dry-run`** lists what a toss would close and every reason it would be refused, closes nothing, and exits 0 if a real toss would proceed or 1 if not. It accepts `--json`.
