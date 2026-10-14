# Change files

Each PR adds one file here describing what it changed for someone using lemonaid.

## Writing one

Name it `YYYY-MM-DD-two-to-six-word-title.md`: the date the work started, then a short
title in lowercase kebab-case, such as `2026-10-14-changes-directory-release.md`.

Its first line names the kind of release the change needs, and the rest is the changelog
entry, in `CHANGES.md`'s style but with no version heading:

```markdown
# Patch

#### Fixed

- **`tell` reaches a Codex lemon whose composer is empty.** It used to report the lemon deaf.
```

- `# Patch`: a fix or minor tweak.
- `# Minor`: a new feature or significant change.
- `# Major`: a breaking change or major milestone.

Write each bullet as one or two sentences: what changed, and the one thing a reader would
otherwise find surprising. A PR that changes `src/`, or
`docs/for-lemons.md` (which ships in the wheel), adds a file; any other PR needs none.

A PR never adds a version to `pyproject.toml`, or edits `CHANGES.md` or a change file
already on main. The `changes` workflow checks this.

## Releasing

A release is made of the change files added since the previous `v*` tag. Its version is
that tag's raised by the highest bump among them, and its notes are their entries in
date order. The `release` workflow cuts one daily and on demand; files keep their names.
Releases through 0.115.3 are in [CHANGES.md](../CHANGES.md). See `docs/development.md`.
