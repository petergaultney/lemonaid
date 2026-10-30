---
type: Notes
created: { at: 2026-10-29T22:00:00-04:00, by: RavenArt }
responsible-parties:
  - Peter Gaultney
contributors:
  - RavenArt
---
# Patch

#### Changed

- **`brief pr add --review <path>` also watches the review doc for all edits.** It adds the doc to Docs with Watch `All edits`, or upgrades an existing `Relay comments` row. Reviewers write findings and re-review verdicts in the body, which a comments-only watch never woke the author for.
