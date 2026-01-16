# Lemonaid Feature Ideas

## "Return to most recent" / `/back` command

When jumping from the lma inbox to a Claude session, sometimes you feel lost and want to go back to where you were.

### Implementation ideas

**Storage:**
- Before `_switch_wezterm_pane()`, save current workspace/pane to SQLite or `~/.local/state/lemonaid/back.json`
- Could be a stack for multi-level back, or just single previous location

**Commands:**
- `lemonaid wezterm back` - switch to the saved previous location
- Could also add `b` keybinding in TUI after switching

**Claude Code integration (`/back` skill):**
- Create a Claude Code skill that runs `lemonaid wezterm back`
- User types `/back` in Claude → switches back to lma inbox or previous location
- Skill definition would go in `~/.claude/skills/` or project `.claude/skills/`

Example skill (`~/.claude/skills/back.md`):
```markdown
---
name: back
description: Return to previous WezTerm location (e.g., lma inbox)
---

Run the command: `lemonaid wezterm back`
```

### Open questions
- Should it be a stack (unlimited back) or just one level?
- What if you `/back` twice - should it ping-pong or go further back?
- Should it integrate with WezTerm's native "last workspace" if that exists?

Status: Worth pursuing - the round-trip UX would be much smoother.
