# Lemonaid Development Guidelines

## Before Committing

1. **Bump the version** in `pyproject.toml` if adding features or fixes
2. **Update CHANGES.md** with a brief description of what changed
3. **Update docs/** if the change affects user-facing behavior (new config options go in `docs/config.md`)
4. **Update README.md** if adding significant features (add to Features list)

## Version Scheme

- Patch (0.1.x → 0.1.y): Bug fixes, minor tweaks
- Minor (0.1.x → 0.2.0): New features, significant changes
- Major (0.x → 1.0): Breaking changes, major milestones

## Project Structure

- `src/lemonaid/` - Main package
- `docs/` - User documentation (tmux.md, wezterm.md, etc.)
- `docs/for-lemons.md` - The programmatic surface, for automated callers
- `CHANGES.md` - Changelog (update with every release)

## Lemonaid knows about directories and terminals

That's the whole model. It has no concept of a git worktree, and adding one is a
change to reject rather than implement.

Anything that creates or removes a directory is a shell command the user declares
per repo root — see `docs/places.md` and `src/lemonaid/places/`. So don't import a
git library, shell out to `git` or `wt`, or branch on whether a repo uses
worktrees. If a feature seems to need that, it needs a new optional hook instead,
and the hook protocol is lines of text rather than JSON so that any tool can
satisfy it.

The notification schema is also not the place to model this: an earlier design
added a `places` table and it was dropped as duplicating what the archive already
records (`cwd` per notification).

## Testing

```bash
uv run pytest
```

## Code Style

Handled by pre-commit hooks (ruff). Just commit and it'll auto-format.
