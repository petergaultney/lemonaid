# Lemonaid Development Guidelines

## Before Committing

1. **Bump the version** in `pyproject.toml` if adding features or fixes
2. **Update CHANGES.md** with a brief description of what changed
3. **Update docs/** if the change affects user-facing behavior
4. **Update README.md** if adding significant features (add to Features list)

## Version Scheme

- Patch (0.1.x → 0.1.y): Bug fixes, minor tweaks
- Minor (0.1.x → 0.2.0): New features, significant changes
- Major (0.x → 1.0): Breaking changes, major milestones

## Project Structure

- `src/lemonaid/` - Main package
- `docs/` - User documentation (tmux.md, wezterm.md, etc.)
- `CHANGES.md` - Changelog (update with every release)

## Testing

```bash
uv run pytest
```

## Code Style

Handled by pre-commit hooks (ruff). Just commit and it'll auto-format.
