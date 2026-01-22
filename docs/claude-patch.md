# Claude Code Notification Patch

Claude Code has a hardcoded 6-second polling interval for firing notification hooks, causing ~10 second delays before you're notified that a session needs attention. Lemonaid can patch the binary to reduce this to 500ms.

See: https://github.com/anthropics/claude-code/issues/5186

## Usage

### From the TUI

When you run `lma`, if Claude Code is unpatched you'll see a message in the status bar:

```
0 unread, 0 read [tmux]  |  Patch Claude for faster notifications
```

Press `P` (capital) to apply the patch. You'll need to restart any running Claude sessions for the change to take effect.

### From the CLI

```bash
# Check current status
lemonaid claude patch-status

# Apply the patch
lemonaid claude patch

# Restore original binary from backup
lemonaid claude patch-restore
```

## How it works

1. Locates the Claude Code binary (typically `~/.local/share/claude/versions/<version>`)
2. Creates a backup with `.backup` suffix
3. Replaces the polling interval constant (e.g., `spB=6000` → `spB=0500`)
4. Re-signs the binary with ad-hoc signature (macOS only, required by Gatekeeper)

## Maintenance

**After Claude Code updates**, you'll need to re-patch:

```bash
lemonaid claude patch
```

The TUI will show the warning again when an update invalidates the patch.

## Technical details

### Version-specific patterns

The minified variable name for the polling interval has changed across versions:

| Version | Original pattern | Patched pattern |
|---------|-----------------|-----------------|
| < 2.1.0 | `ewD=6000` | `ewD=0500` |
| >= 2.1.0 | `spB=6000` | `spB=0500` |

If a future version changes the pattern again, lemonaid will report status as "unknown" and we'll need to:

1. Find the new pattern: `grep -boa 'setInterval' ~/.local/share/claude/versions/<version>` and look for notification-related intervals
2. Update `get_pattern_for_version()` in `src/lemonaid/claude/patcher.py`

### macOS code signing

Modifying the binary invalidates Apple's code signature, causing Gatekeeper to kill the process on launch. The patcher automatically re-signs with an ad-hoc signature:

```bash
codesign --sign - --force <binary>
```

This creates a local signature that satisfies Gatekeeper without requiring a developer certificate.

### Binary locations

The patcher searches these locations (in order):

**macOS:**
- `~/Library/Application Support/claude/versions/`
- `~/.local/share/claude/versions/`

**Linux:**
- `~/.local/share/claude/versions/`
- `~/.claude/versions/`

Falls back to resolving `claude` from PATH if not found.
