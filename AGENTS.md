# Lemonaid Development Guidelines

## Never touch the live install or its state

The maintainer's installed `lemonaid` runs from a checkout, and every hook on the machine
writes their real inbox. A lemon working on lemonaid must not change either.

- **Work in a separate worktree or clone.** Never edit, switch branches in, or run
  `uv sync` in the checkout the tool is installed from (`uv tool list
  --show-paths` / the `.pth` under `~/.local/share/uv/tools/lemonaid` says which).
  For example, `git worktree add ../lemonaid-<branch> -b <branch> main`.
- **Run anything outside pytest through `scripts/sandbox`**: `scripts/sandbox
  lemonaid ...`, `scripts/sandbox lma`. It points the database, config, state
  directory, and tmux at `.z/sandbox/` in your worktree, seeded once from a
  read-only snapshot. A bare `uv run lemonaid ...` writes the live inbox.
- **Never open the live database, config, or `~/.local/state/lemonaid` for
  writing, and never touch the real tmux server's options or sessions,** without
  asking the maintainer first - including to repair something you broke. Say what
  happened and what you'd do.
- To show the maintainer a change working, give them `scripts/sandbox attach` or
  `scripts/sandbox lma` from the worktree. Making a branch live is their step.

## Before Committing

1. **Bump the version** in `pyproject.toml` if adding features or fixes
2. **Update CHANGES.md** with a brief description of what changed
3. **Update docs/** if the change affects user-facing behavior (new config options go in `docs/config.md`)
4. **Update README.md** if adding significant features (add to Features list)

Only a change to the product gets a version bump and a CHANGES.md entry. A change that touches only docs or tests gets neither.

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
