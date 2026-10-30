---
type: Notes
created: { at: 2026-10-29T21:55:00-04:00, by: RavenArt }
responsible-parties:
  - Peter Gaultney
contributors:
  - RavenArt
---
# Minor

#### Added

- **Briefs nobody uses move to the attic.** Once a day, any brief unused for `[brief] archive_idle_days` (default 14) moves with its inbox to `~/.lemons/attic/YYYY-MM/`, and `place toss` does the same for the lemons it ends. `lemonaid brief archive` does it by hand, for one brief or with `--idle-days D`, and `lemonaid brief revive` brings one back. An archived brief keeps its Lemon-ID, so lookups by ID still find it, but nothing that scans attached briefs reads it again.
