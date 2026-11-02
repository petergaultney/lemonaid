---
type: Notes
created: { at: 2026-11-02T09:00:00-05:00, by: WorthAdd }
responsible-parties:
  - Peter Gaultney
contributors:
  - WorthAdd
---
# Vendored diff-stats

Copy of `diff-stats/` from `93 System software` (the `system-software` repo), without its `tests/`, `SKILL.md` and Obsidian folder notes. CI runs it from `.github/workflows/diff-stats.yml` to keep the diff breakdown in each PR description current.

Re-copy from a checkout of that repo:

```sh
rsync -a --exclude=__pycache__ --exclude=tests --exclude=SKILL.md --exclude=diff-stats.md --exclude=src.md --exclude=diff_stats.md "<93 System software>/diff-stats/" tools/diff-stats/
```

Do not edit the copy here; change it upstream and re-copy.
