---
type: Notes
created: { at: 2026-10-30T21:18:20-04:00, by: HeavyWeb }
responsible-parties:
  - Peter Gaultney
contributors:
  - HeavyWeb
---
# Patch

#### Fixed

- **A PR's review doc wakes its lemon for body edits even when its Docs row says `Relay comments`.** Reviewers write findings and verdicts in the body, so a doc named in a PR row's Review cell is always watched for all edits.
- **`brief new --child --pr <url> --output-doc <path>` names the doc in that PR's empty Review cell in the parent's and `--author`'s briefs.** Before, an author whose PR row had no Review link was never woken by its reviewer's findings.
