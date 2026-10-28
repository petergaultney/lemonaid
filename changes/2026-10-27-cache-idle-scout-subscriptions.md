---
type: Notes
created: { at: 2026-10-27T20:11:12-04:00, by: ChurnOdd }
responsible-parties:
  - Peter Gaultney
contributors:
  - ChurnOdd
---

# Patch

#### Fixed

- Idle unified watchers reuse parsed subscriptions while their brief and saved state are unchanged, reducing CPU use without slowing inbox checks.
